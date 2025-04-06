import { loadTheme, toggleMode } from "/static/js/theme.js";

function sharePage() {
    if (navigator.share) {
        navigator
            .share({
                title: document.title,
                url: window.location.href,
            })
            .then(() => {
                console.log("Thanks for sharing!");
            })
            .catch(console.error);
    } else {
        alert("Share not supported on this browser, do it the old way.");
    }
}

const spinner = document.getElementById("loading-spinner");
const playerButton = document.querySelector("#play-button"),
    audio = document.querySelector("audio"),
    timeline = document.querySelector("#timeline"),
    soundButton = document.querySelector("#sound-button"),
    currentTimeDisplay = document.getElementById("current-time"),
    playIcon = `play_arrow`,
    pauseIcon = `stop`,
    volumeOn = `volume_up`,
    muteIcon = `volume_off`;
let srcNode = null;
var audioContext;

audio.addEventListener("loadstart", (event) => {
    spinner.style.display = "block";
    timeline.disabled = true;
    soundButton.disabled = true;
    playerButton.disabled = true;
});

audio.addEventListener("seeking", (event) => {
    spinner.style.display = "block";
});

audio.addEventListener("waiting", (event) => {
    spinner.style.display = "block";
});

// Hide spinner once data is ready
audio.addEventListener("canplaythrough", (event) => {
    spinner.style.display = "none";
    timeline.disabled = false;
    soundButton.disabled = false;
    playerButton.disabled = false;
});

// Also hide on error to avoid infinite spin
audio.addEventListener("error", (event) => {
    spinner.style.display = "none";
    timeline.disabled = false;
    soundButton.disabled = false;
    playerButton.disabled = false;
});

function updateTime() {
    if (!isFinite(audio.duration)) {
        // currentTimeDisplay.textContent = "Live";
        return;
    }

    let currentMinutes = Math.floor(audio.currentTime / 60);
    let currentSeconds = Math.floor(audio.currentTime - currentMinutes * 60);
    currentMinutes = currentMinutes < 10 ? "0" + currentMinutes : currentMinutes;
    currentSeconds = currentSeconds < 10 ? "0" + currentSeconds : currentSeconds;

    // currentTimeDisplay.textContent = `${currentMinutes}:${currentSeconds}`;

    timeline.value = parseInt((audio.currentTime / audio.duration) * 100);
}


function toggleAudio() {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const playIconEl = document.getElementById("play-icon");

    soundButton.addEventListener("click", toggleSound);

    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }

    if (!srcNode) {
        srcNode = audioContext.createMediaElementSource(audio);

        const analyser = audioContext.createAnalyser();
        srcNode.connect(analyser);
        analyser.connect(audioContext.destination);

        const fftSize = window.innerWidth > 800 ? 512 : 256;
        analyser.fftSize = fftSize;
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const canvasWidth = canvas.clientWidth * window.devicePixelRatio;
        const canvasHeight = canvas.clientHeight * window.devicePixelRatio;
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;

        const WIDTH = canvas.width;
        const HEIGHT = canvas.height;
        const barWidth = (WIDTH / bufferLength) * 2.5;

        function renderFrame() {
            requestAnimationFrame(renderFrame);
            analyser.getByteFrequencyData(dataArray);
            const articleBackgroundColor = getComputedStyle(document.getElementById("main-play-article")).backgroundColor;
            ctx.fillStyle = articleBackgroundColor;
            ctx.fillRect(0, 0, WIDTH, HEIGHT);

            let x = 0;
            for (let i = 0; i < bufferLength; i++) {
                const barHeight = window.innerWidth > 800 ? Math.min(dataArray[i] / 4, HEIGHT - 10) : dataArray[i] / 2;
                ctx.fillStyle = getComputedStyle(document.getElementById("header")).backgroundColor;
                ctx.fillRect(x, HEIGHT - barHeight, barWidth, barHeight);
                x += barWidth + 1;
            }
        }

        renderFrame();
    }
    if (audio.paused) {
        audio.play().then(() => {
            playIconEl.textContent = "pause_circle";
        }).catch((err) => {
            console.error("Playback failed:", err);
        });
    } else {
        audio.pause();
        playIconEl.textContent = "play_circle";
    }
}


function changeTimelinePosition() {
    const percentagePosition = (100 * audio.currentTime) / audio.duration;
    timeline.value = percentagePosition;
    updateTime();
}

audio.addEventListener("timeupdate", (event) => {
    updateTime();
    changeTimelinePosition();
});

audio.addEventListener("ended", (event) => {
});

timeline.addEventListener("input", (event) => {
    if (audio.readyState >= 2 && !isNaN(audio.duration)) {
        const percent = parseFloat(timeline.value);
        const time = (percent / 100.0) * audio.duration;
        audio.currentTime = time;
        updateTime();
    }
});

function toggleSound() {
    audio.muted = !audio.muted;
}

document.addEventListener('DOMContentLoaded', async function () {
    const fileName = document.title;

    await Promise.all([
        updateEventCount(),
        updateRecordingStats(fileName),
    ]);

    setInterval(updateEventCount, 1000 * 60);
    setInterval(() => updateRecordingStats(fileName), 1000 * 60);
});

document.addEventListener("DOMContentLoaded", function () {
    loadTheme();

    // this.getElementById('toggle-theme').addEventListener('click', toggleMode);
    playerButton.addEventListener("click", toggleAudio);

    const shareButton = document.getElementById("share-button");
    shareButton.addEventListener("click", function () {
        sharePage();
    });
});

async function updateEventCount() {
    const response = await fetch('/get_event_count');
    if (!response.ok) throw new Error('Failed to fetch event count');
    const data = await response.json();
    const broadcastCount = data.broadcast_count;
    const scheduledBroadcastCount = data.scheduled_broadcast_count;

    document.querySelectorAll("#event-tooltip-status").forEach(eventTooltipStatus => {
        let message = "";
        if (broadcastCount >= 1)
            message += `${broadcastCount} active broadcast${broadcastCount > 1 ? "s" : ""}<br>`;
        if (scheduledBroadcastCount >= 1)
            message += `${scheduledBroadcastCount} scheduled broadcast${scheduledBroadcastCount > 1 ? "s" : ""}`;
        if (broadcastCount + scheduledBroadcastCount === 0)
            message = "No broadcasts currently<br>online or events scheduled.";
        eventTooltipStatus.innerHTML = message;
    });

    document.querySelectorAll("#event-count").forEach(eventCount => {
        if (broadcastCount + scheduledBroadcastCount === 0) {
            eventCount.classList.add('hidden');
            return;
        }else{
            eventCount.classList.remove('hidden');
        }
        eventCount.textContent = broadcastCount + scheduledBroadcastCount;
    });
}

async function updateRecordingStats(fileName) {
    try {
        const response = await fetch(`/get_broadcast_data`);
        if (!response.ok) throw new Error('Failed to fetch recording stats');

        const data = await response.json();

        data.forEach(broadcast_data => {
            if (broadcast_data.host === fileName) {
                const listenersElem = document.querySelector('#listeners');
                const listenerPeakElem = document.querySelector('#listener-peak');
                const lengthElem = document.querySelector('#length');
                lengthElem.textContent = `${broadcast_data.length}`;
                listenersElem.textContent = `${broadcast_data.listeners}`;
                listenerPeakElem.textContent = `${broadcast_data.listener_peak}`;
            }
        });
    } catch (error) {
        console.error('Error updating recording stats:', error);
    }
}
