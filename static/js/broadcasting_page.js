import { loadTheme, toggleMode } from "/static/js/theme.js";

let mediaRecorder;
let ws;
let audioContext;
let gainNode;
let sourceNode;
let isMuted = false;
let analyser;
let dataArray;
let canvas;
let canvasCtx;
let timeout;
let recordedChunks = [];

function validateHostName() {
    const hostInput = document.getElementById('host');
    let hostValue = hostInput.value.toLowerCase();
    hostValue = hostValue.replace(/[<>:"/\\|?*]/g, '');
    hostValue = hostValue.replace(/ /g, '_');
    hostValue = hostValue.replace(/^_+|_+$/g, '');
    hostValue = hostValue.replace(/\d/g, '');
    hostInput.value = hostValue;
}

function validateDescription() {
    const descriptionInput = document.getElementById('description');
    let descriptionValue = descriptionInput.value;
    descriptionValue = descriptionValue.replace(/&/g, 'and');
    descriptionValue = descriptionValue.replace(/[/\\]/g, ' or ');
    descriptionValue = descriptionValue.replace(/[<>:"|?*]/g, '_');
    descriptionValue = descriptionValue.replace(/[^a-zA-Z\s]/g, '');
    descriptionValue = descriptionValue.replace(/^_+|_+$/g, '');
    descriptionInput.value = descriptionValue;
}

function share() {
    const isPrivate = document.getElementById('isPrivate').checked;
    const host = document.getElementById('host').value;
    const description = document.getElementById('description').value;
    let url = "";
    if (isPrivate) {
        url = "https://broadcast.hbni.net/" + host;
    } else {
        url = window.location.origin + "/listeners_page";
    }
    if (navigator.share) {
        navigator.share({
            title: "HBNI Audio Listeners Page",
            text: "Listen to this broadcast on the HBNI Audio Listeners page!",
            url: url
        });
    } else {
        navigator.clipboard.writeText(`${host} just started a broadcast with the description, ${description}. - Visit here: ${url}`)
            .then(() => {
                const snackbar = document.getElementById("copied-to-clipboard");
                snackbar.classList.add("show");
                setTimeout(() => snackbar.classList.remove("show"), 3000);
            })
            .catch((error) => console.error("Error copying to clipboard:", error));
        ui("#copied-to-clipboard");
    }
}

async function submitSchedule() {
    const host = document.getElementById("schedule-host").value;
    const description = document.getElementById("schedule-description").value;
    const startTime = document.getElementById("date-time-picker").value;

    if (!host || !description || !startTime) {
        alert("Please provide all the required fields.");
        return;
    }

    // Send the data to the server
    const response = await fetch("/schedule_broadcast", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ host, description, startTime })
    });

    if (response.ok) {
        ui("#schedule-dialog");
        ui("#schedule-success");
    } else {
        ui("#schedule-error");
    }
}

document.getElementById("startBroadcast").disabled = true;

async function checkPassword() {
    const password = document.getElementById("password").value;

    try {
        const response = await fetch("/validate-password", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ password })
        });

        const result = await response.json();

        if (result.success) {
            localStorage.setItem("broadcastToken", result.token); // Save token securely
            document.getElementById("startBroadcast").disabled = false;
            document.getElementById("scheduleBroadcast").disabled = false;
            ui("#correct-password");
        } else {
            ui("#incorrect-password");
            document.getElementById("startBroadcast").disabled = true;
            document.getElementById("scheduleBroadcast").disabled = true;
        }
    } catch (error) {
        console.error("Error validating password:", error);
    }
}

document.getElementById("password").addEventListener("input", async () => {
    clearTimeout(timeout);
    timeout = setTimeout(checkPassword, 3000);
});

document.getElementById("host").addEventListener("input", () => {
    const host = document.getElementById("host").value;
    const description = document.getElementById("description").value;
    const password = document.getElementById("password").value;
    if (!host || !description || !password) {
        document.getElementById("startBroadcast").disabled = true;
    } else {
        document.getElementById("startBroadcast").disabled = false;
    }
});

document.getElementById("description").addEventListener("input", () => {
    const host = document.getElementById("description").value;
    const description = document.getElementById("description").value;
    const password = document.getElementById("password").value;
    if (!host || !description || !password) {
        document.getElementById("startBroadcast").disabled = true;
    } else {
        document.getElementById("startBroadcast").disabled = false;
    }
});

document.getElementById('startBroadcast').addEventListener('click', async () => {
    try {
        const host = document.getElementById('host').value;
        const description = document.getElementById('description').value;
        const password = document.getElementById('password').value;
        const isPrivate = document.getElementById('isPrivate').checked;

        if (!host || !description || !password) {
            alert("Please provide all the required fields.");
            return;
        }

        // Capture audio
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // Initialize audio processing
        audioContext = new AudioContext();
        analyser = audioContext.createAnalyser();
        sourceNode = audioContext.createMediaStreamSource(stream);
        gainNode = audioContext.createGain();
        const destinationNode = audioContext.createMediaStreamDestination();

        // Connect the source to gainNode, analyser, and destination
        sourceNode.connect(gainNode);
        gainNode.connect(analyser);
        gainNode.connect(destinationNode);

        // Use the processed stream for MediaRecorder
        const processedStream = destinationNode.stream;

        // Configure analyser for visualization
        analyser.fftSize = 256;
        const bufferLength = analyser.frequencyBinCount;
        dataArray = new Uint8Array(bufferLength);

        visualize();

        // Initialize secure WebSocket connection to Tornado backend
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        ws = new WebSocket(`${protocol}://${window.location.host}/broadcast_ws`);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            // Send metadata to the server
            const metadata = {
                host: host,
                description: description,
                password: password,
                isPrivate: isPrivate
            };

            ws.send(JSON.stringify(metadata));
            ui("#broadcast-started");

            // Disable inputs after starting
            document.getElementById('startBroadcast').disabled = true;
            document.getElementById('stopBroadcast').disabled = false;
            document.getElementById('isPrivate').disabled = true;
            document.getElementById('password').disabled = true;
            document.getElementById('muteToggle').disabled = false;
            document.getElementById('volumeControl').disabled = false;

            const options = { mimeType: 'audio/webm;codecs=opus' };

            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                console.error(`MIME type ${options.mimeType} is not supported.`);
                alert("The specified audio format is not supported by your browser.");
                return;
            }

            mediaRecorder = new MediaRecorder(processedStream, options);

            mediaRecorder.ondataavailable = (event) => {
                if (ws.readyState === WebSocket.OPEN) {
                    if (!isMuted) {
                        // Convert Blob to ArrayBuffer and then send
                        event.data.arrayBuffer().then(buffer => {
                            ws.send(new Uint8Array(buffer));
                        });
                        // Save data locally
                        recordedChunks.push(event.data);
                    } else {
                        // Send silence if muted
                        const silenceBuffer = new ArrayBuffer(0);
                        ws.send(new Uint8Array(silenceBuffer));
                    }
                }
            };

            mediaRecorder.start(250); // Send data every 250ms
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
        };

        ws.onclose = () => {
            // Enable inputs after stopping
            document.getElementById('startBroadcast').disabled = false;
            document.getElementById('stopBroadcast').disabled = true;
            document.getElementById('isPrivate').disabled = false;
            document.getElementById('password').disabled = false;
            document.getElementById('muteToggle').disabled = true;
            document.getElementById('volumeControl').disabled = true;

            // Stop the audio stream
            stream.getTracks().forEach(track => track.stop());
        };
    } catch (error) {
        alert("Error accessing microphone: " + error.message);
    }
});

document.getElementById('stopBroadcast').addEventListener('click', () => {
    if (ws) {
        ws.close();
    }

    if (mediaRecorder) {
        mediaRecorder.stop();
    }
    if (audioContext) {
        audioContext.close();
    }

    canvasCtx.clearRect(0, 0, canvas.width, canvas.height);

    if (recordedChunks.length > 0) {
        const audioBlob = new Blob(recordedChunks, { type: 'audio/webm' });
        ui("#save-broadcast-dialog");
        const host = document.getElementById('host').value;
        document.getElementById('broadcast-file-name').innerText = `${host.charAt(0).toUpperCase() + host.slice(1)} - ${document.getElementById('description').value} - ${new Date().toISOString().slice(0, 10)}.webm`;

        document.getElementById('save-broadcast-btn').addEventListener('click', () => {
            const downloadLink = document.createElement('a');
            downloadLink.href = URL.createObjectURL(audioBlob);
            downloadLink.download = `${host.charAt(0).toUpperCase() + host.slice(1)} - ${document.getElementById('description').value} - ${new Date().toISOString().slice(0, 10)}.webm`;
            downloadLink.click();

            ui("#save-broadcast-dialog");
        });
    }

    recordedChunks = []; // Clear recorded chunks
});

document.getElementById('muteToggle').addEventListener('click', () => {
    if (gainNode) {
        isMuted = !isMuted;

        if (isMuted) {
            // Stop sending audio to the WebSocket and visualizer
            // sourceNode.disconnect(analyser);
            sourceNode.disconnect(gainNode);
            ws.send(JSON.stringify({ type: "mute" })); // Notify server if needed
        } else {
            // Resume sending audio to the WebSocket and visualizer
            // sourceNode.connect(analyser);
            sourceNode.connect(gainNode);
            ws.send(JSON.stringify({ type: "unmute" })); // Notify server if needed
        }

        gainNode.gain.value = isMuted ? 0 : parseFloat(document.getElementById('volumeControl').value);

        document.getElementById('muteToggle').querySelector('i.mic-icon').innerText = isMuted ? 'mic_off' : 'mic';
        document.getElementById('muteToggle').querySelector('i.pause-icon').innerText = isMuted ? 'play_arrow' : 'pause';
    }
});

document.getElementById('volumeControl').addEventListener('input', (event) => {
    if (gainNode && !isMuted) {
        gainNode.gain.value = parseFloat(event.target.value);
    }
});

function visualize() {
    const WIDTH = canvas.width;
    const HEIGHT = canvas.height;
    const barWidth = (WIDTH / dataArray.length) * 2.5;

    function draw() {
        requestAnimationFrame(draw);

        analyser.getByteFrequencyData(dataArray);

        // Clear the canvas
        var articleBackgroundColor = window.getComputedStyle(
            document.getElementById("main-article")
        ).backgroundColor;

        canvasCtx.fillStyle = articleBackgroundColor;
        canvasCtx.fillRect(0, 0, WIDTH, HEIGHT);

        let x = 0;

        // Draw the frequency bars
        for (let i = 0; i < dataArray.length; i++) {
            const barHeight = dataArray[i] / 2;

            // Color logic (gradient based on frequency intensity)
            const r = (barHeight + 100) % 255;
            const g = (barHeight * 2) % 255;
            const b = (barHeight * 3) % 255;

            var header = document.getElementById("header");
            var headerStyle = getComputedStyle(header);
            var headerBackgroundColor = headerStyle.backgroundColor;
            canvasCtx.fillStyle = headerBackgroundColor;
            canvasCtx.fillRect(x, HEIGHT - barHeight, barWidth, barHeight);

            x += barWidth + 1;
        }
    }

    draw();
}

document.addEventListener('DOMContentLoaded', function () {
    loadTheme();

    const host = localStorage.getItem('host') || "";
    document.getElementById('host').value = host;
    document.getElementById('host').addEventListener('input', function () {
        localStorage.setItem('host', this.value);
        validateHostName()
    });

    const description = localStorage.getItem('description') || "";
    document.getElementById('description').value = description;
    document.getElementById('description').addEventListener('input', function () {
        localStorage.setItem('description', this.value);
        validateDescription()
    });

    const password = localStorage.getItem('password') || "";
    document.getElementById('password').value = password;
    document.getElementById('password').addEventListener('input', function () {
        localStorage.setItem('password', this.value);
    });

    document.getElementById('toggle-theme').addEventListener('click', toggleMode);

    const submitScheduleButton = document.getElementById('submit-schedule-button');
    submitScheduleButton.addEventListener('click', function () {
        submitSchedule();
    });

    const shareButton = document.getElementById('share-button');
    shareButton.addEventListener('click', function () {
        share();
    });

    const broadcastDetails = document.getElementById('broadcast-details');
    const broadcastControls = document.getElementById('broadcast-controls');

    broadcastDetails.open = localStorage.getItem('broadcast-details-open') === 'true' ? true : false;
    broadcastControls.open = localStorage.getItem('broadcast-controls-open') === 'true' ? true : false;

    broadcastDetails.addEventListener('click', function () {
        localStorage.setItem('broadcast-details-open', !broadcastDetails.open);
    });

    broadcastControls.addEventListener('click', function () {
        localStorage.setItem('broadcast-controls-open', !broadcastControls.open);
    });

    // Initialize canvas and audio context
    canvas = document.getElementById("canvas");
    canvasCtx = canvas.getContext("2d");

    // Set up the canvas for visualization
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
    canvasCtx.scale(dpr, dpr);

    const searchInput = document.getElementById('search');

    const header = document.getElementById('main-header');

    const observer = new IntersectionObserver(function (entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                header.style.display = 'block';
            } else {
                header.style.display = 'none';
            }
        });
    });
    if (document.getElementById('password').value !== "") {
        checkPassword();
    }
    flatpickr("#date-time-picker", {
        enableTime: true,
        dateFormat: "Y-m-d H:i",
        altInput: true,
        altFormat: "F j, Y H:i",
        defaultDate: new Date(),
    });
});
