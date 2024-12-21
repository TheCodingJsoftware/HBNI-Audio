const mode = () => {
    let currentMode = localStorage.getItem("mode") || "dark";
    let newMode = currentMode === "dark" ? "light" : "dark";
    localStorage.setItem("mode", newMode); // Save mode to localStorage
    ui("mode", newMode);
    updateIcon(newMode);
    updateImageSource();
    document.documentElement.classList.toggle("dark", newMode === "dark");
};

function updateImageSource() {
    const mode = localStorage.getItem('mode') || 'light';
    const images = document.querySelectorAll('img[id^="recording-card-image"]');
    images.forEach(image => {
        image.src = mode === 'dark' ? '/static/hbni_logo_dark.png' : '/static/hbnilogo.png';
    });
}

const updateIcon = (mode) => {
    const iconElements = document.querySelectorAll('#toggle-theme i');
    iconElements.forEach(iconElement => {
        iconElement.textContent = mode === "dark" ? "light_mode" : "dark_mode";
    });
};

function shareUpcomingBroadcast(text) {
    // Check if the Web Share API is available
    if (navigator.share) {
        const url = window.location.origin + "/listeners_page";
        const shareData = {
            title: "HBNI Audio Listeners Page",
            text: text,
            url: url
        };

        navigator.share(shareData)
            .then(() => console.log("Shared successfully!"))
            .catch((error) => {
                console.error("Error sharing:", error);
                alert("Could not share the broadcast.");
            });
    } else {
        // Fallback to clipboard if Web Share API is not supported
        navigator.clipboard.writeText(`${text} - Visit here: ${window.location.origin}/listeners_page`)
            .then(() => {
                const snackbar = document.getElementById("copied-to-clipboard");
                snackbar.classList.add("show");
                setTimeout(() => snackbar.classList.remove("show"), 3000);
            })
            .catch((error) => console.error("Error copying to clipboard:", error));
        ui("#copied-to-clipboard");
    }
}

function copyUpcomingBroadcastToClipboard(text) {
    navigator.clipboard.writeText(`${text} - Visit here: ${window.location.origin}/listeners_page`);
    ui("#copied-to-clipboard");
}

document.addEventListener('DOMContentLoaded', function () {
    let savedMode = localStorage.getItem("mode") || "light";
    ui("mode", savedMode);
    updateIcon(savedMode);
    document.documentElement.classList.toggle("dark", savedMode === "dark");
    updateImageSource();
});
