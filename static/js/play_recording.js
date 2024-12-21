document.addEventListener("DOMContentLoaded", function () {
    let savedMode = localStorage.getItem("mode") || "light";
    ui("mode", savedMode);
    updateIcon(savedMode);
    const downloadButton = document.getElementById("download-button");

    downloadButton.addEventListener("click", function () {
        const url = this.getAttribute("data-url");
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", "");
        link.click();
        console.log(url);
    });
});
const mode = () => {
    let currentMode = localStorage.getItem("mode") || "light";
    let newMode = currentMode === "dark" ? "light" : "dark";
    localStorage.setItem("mode", newMode); // Save mode to localStorage
    ui("mode", newMode);
    updateIcon(newMode);
};

const updateIcon = (mode) => {
    const iconElements = document.querySelectorAll("#toggle-theme i");
    iconElements.forEach((iconElement) => {
        iconElement.textContent = mode === "dark" ? "light_mode" : "dark_mode";
    });
    // const musicNote = document.querySelector(".music-note");
    // musicNote.style.color = "var(--on-primary)";
};

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

function updateTime() {
    var audio = document.querySelector("audio");
    let currentMinutes = Math.floor(audio.currentTime / 60);
    let currentSeconds = Math.floor(audio.currentTime - currentMinutes * 60);
    let durationMinutes = Math.floor(audio.duration / 60);
    let durationSeconds = Math.floor(audio.duration - durationMinutes * 60);

    currentMinutes =
        currentMinutes < 10 ? "0" + currentMinutes : currentMinutes;
    currentSeconds =
        currentSeconds < 10 ? "0" + currentSeconds : currentSeconds;
    durationMinutes =
        durationMinutes < 10 ? "0" + durationMinutes : durationMinutes;
    durationSeconds =
        durationSeconds < 10 ? "0" + durationSeconds : durationSeconds;

    currentTimeDisplay.textContent = `${currentMinutes}:${currentSeconds}`;
    totalTimeDisplay.textContent = `${durationMinutes}:${durationSeconds}`;

    timeline.value = (audio.currentTime / audio.duration) * 100;
}

audio.addEventListener("timeupdate", updateTime);

function toggleAudio() {
    var audio = document.querySelector("audio");
    var canvas = document.querySelector("canvas");
    var ctx = canvas.getContext("2d");

    var soundButton = document.querySelector("#sound-button");

    soundButton.addEventListener("click", toggleSound);

    if (audio.paused) {
        audio.play();
    } else {
        audio.pause();
    }
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        var src = audioContext.createMediaElementSource(audio); // Fixed variable name here

        var analyser = audioContext.createAnalyser();

        src.connect(analyser);
        analyser.connect(audioContext.destination);

        var fftSize = 256; // Default value for mobile

        // Check if the device is a PC (assuming PC if screen width > 768px)
        if (window.innerWidth > 800) {
            fftSize = 512; // Change to 2048 for PC
        }
        analyser.fftSize = fftSize;
        var bufferLength = analyser.frequencyBinCount;

        var dataArray = new Uint8Array(bufferLength);

        // Get the device pixel ratio
        var devicePixelRatio = window.devicePixelRatio || 1;

        // Adjust canvas dimensions based on device pixel ratio
        var canvasWidth = canvas.clientWidth * devicePixelRatio;
        var canvasHeight = canvas.clientHeight * devicePixelRatio;

        canvas.width = canvasWidth;
        canvas.height = canvasHeight;

        var WIDTH = canvas.width;
        var HEIGHT = canvas.height;

        var barWidth = (WIDTH / bufferLength) * 2.5;
        var barHeight;
        var x = 0;

        function renderFrame() {
            requestAnimationFrame(renderFrame);

            x = 0;

            analyser.getByteFrequencyData(dataArray);

            var articleBackgroundColor = window.getComputedStyle(
                document.getElementById("main-article")
            ).backgroundColor;

            ctx.fillStyle = articleBackgroundColor;
            ctx.fillRect(0, 0, WIDTH, HEIGHT);

            for (var i = 0; i < bufferLength; i++) {
                if (window.innerWidth > 800) {
                    barHeight = dataArray[i] / 4;
                    barHeight = Math.min(barHeight, HEIGHT - 10);
                } else {
                    barHeight = dataArray[i] / 2;
                }

                var r = barHeight + 25 * (i / bufferLength);
                var g = barHeight + 250 * (i / bufferLength);
                var b = barHeight + 50 * (i / bufferLength);

                var header = document.getElementById("header");
                var headerStyle = getComputedStyle(header);
                var headerBackgroundColor = headerStyle.backgroundColor;
                ctx.fillStyle = headerBackgroundColor;
                ctx.fillRect(x, HEIGHT - barHeight, barWidth, barHeight);

                x += barWidth + 1;
            }
        }

        audio.play();
        renderFrame();
    }
}

playerButton.addEventListener("click", toggleAudio);

function changeTimelinePosition() {
    const percentagePosition = (100 * audio.currentTime) / audio.duration;
    timeline.value = percentagePosition;
}

audio.ontimeupdate = changeTimelinePosition;

function audioEnded() { }
audio.onended = audioEnded;

function changeSeek() {
    const time = (timeline.value * audio.duration) / 100;
    audio.currentTime = time;
}

timeline.addEventListener("change", changeSeek);
var audioContext;

function toggleSound() {
    audio.muted = !audio.muted;
}