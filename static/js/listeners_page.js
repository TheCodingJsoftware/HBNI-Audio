let fetchInterval = null;

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

async function fetchBroadcastData() {
    try {
        const response = await fetch('/get_broadcast_data');
        if (!response.ok) throw new Error('Failed to fetch broadcast stats');
        const broadcast_data = await response.json();

        // If there are no broadcasts online, stop the interval
        if (!broadcast_data || broadcast_data.length === 0) {
            console.log("No broadcasts online. Stopping updates.");
            if (fetchInterval) clearInterval(fetchInterval);
            return;
        }

        broadcast_data.forEach(broadcast => {
            const listenersElem = document.querySelector(`#listeners-${broadcast.host}`);
            const listenerPeakElem = document.querySelector(`#listener-peak-${broadcast.host}`);
            const lengthElem = document.querySelector(`#length-${broadcast.host}`);

            if (listenersElem) listenersElem.textContent = `${broadcast.listeners}`;
            if (listenerPeakElem) listenerPeakElem.textContent = `${broadcast.listener_peak}`;
            if (lengthElem) lengthElem.textContent = `${broadcast.length}`;
        });
    } catch (error) {
        console.error('Error fetching broadcast stats:', error);
    }
}


// Periodically fetch updates
document.addEventListener('DOMContentLoaded', function () {
    let savedMode = localStorage.getItem("mode") || "light";
    ui("mode", savedMode);
    updateIcon(savedMode);
    document.documentElement.classList.toggle("dark", savedMode === "dark");
    updateImageSource();
    document.querySelectorAll('audio').forEach(audioElement => {
        audioElement.onerror = function () {
            alert('The audio stream is unavailable because it is served over an insecure connection. Please contact support for assistance.');
        };
    });

});

document.addEventListener('DOMContentLoaded', async function () {
    try {
        const response = await fetch('/get_broadcast_data');
        if (!response.ok) throw new Error('Failed to fetch broadcast stats');
        const broadcast_data = await response.json();

        if (broadcast_data && broadcast_data.length > 0) {
            fetchInterval = setInterval(fetchBroadcastData, 5000);
        }
    } catch (error) {
        console.error('Error during initial fetch:', error);
    }
});