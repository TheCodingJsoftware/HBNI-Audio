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
    totalTimeDisplay = document.getElementById("total-time"),
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
    let currentMinutes = Math.floor(audio.currentTime / 60);
    let currentSeconds = Math.floor(audio.currentTime - currentMinutes * 60);
    let durationMinutes = Math.floor(audio.duration / 60);
    let durationSeconds = Math.floor(audio.duration - durationMinutes * 60);

    currentMinutes = currentMinutes < 10 ? "0" + currentMinutes : currentMinutes;
    currentSeconds = currentSeconds < 10 ? "0" + currentSeconds : currentSeconds;
    durationMinutes = durationMinutes < 10 ? "0" + durationMinutes : durationMinutes;
    durationSeconds = durationSeconds < 10 ? "0" + durationSeconds : durationSeconds;

    currentTimeDisplay.textContent = `${currentMinutes}:${currentSeconds}`;
    totalTimeDisplay.textContent = `${durationMinutes}:${durationSeconds}`;

    timeline.value = parseInt((audio.currentTime / audio.duration) * 100);
}

function toggleAudio() {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");

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
        audio.play();
    } else {
        audio.pause();
    }
}

playerButton.addEventListener("click", toggleAudio);

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

document.addEventListener("DOMContentLoaded", function () {
    loadTheme();
    const downloadButton = document.getElementById("download-button");
    downloadButton.addEventListener("click", function () {
        const url = this.getAttribute("data-url");
        const name = this.getAttribute("data-name");
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", name);
        document.body.appendChild(link); // Required for Firefox
        link.click();
        document.body.removeChild(link);
    });
    // this.getElementById('toggle-theme').addEventListener('click', toggleMode);

    const shareButton = document.getElementById("share-button");
    shareButton.addEventListener("click", function () {
        sharePage();
    });
});

async function updateRecordingStats(fileName) {
    try {
        const response = await fetch(`/recording_stats/${decodeURIComponent(fileName)}`);
        if (!response.ok) throw new Error('Failed to fetch recording stats');

        const data = await response.json();

        const visitCountElem = document.querySelector('#visit-count');
        const latestVisitElem = document.querySelector('#latest-visit');

        if (visitCountElem) {
            visitCountElem.textContent = `${data.visit_count}`;
        }

        if (latestVisitElem) {
            latestVisitElem.innerHTML = `${data.latest_visit}`;
        }
    } catch (error) {
        console.error('Error updating recording stats:', error);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const fileName = document.title;
    setInterval(() => updateRecordingStats(fileName), 1000 * 60);
});
