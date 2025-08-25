import { loadTheme, toggleMode } from "/static/js/theme.js";
import "flatpickr";
require("flatpickr/dist/themes/dark.css");

if ('serviceWorker' in navigator && 'Notification' in window) {
    import("firebase/app").then(({ initializeApp }) => {
        import("firebase/messaging").then(({ getMessaging, getToken, onMessage }) => {
            import('./config').then(({ firebaseConfig, vapidKey }) => {
                const app = initializeApp(firebaseConfig);
                const messaging = getMessaging(app);

                // Listen for incoming messages
                onMessage(messaging, (payload) => {
                    console.log('Foreground notification received:', payload);

                    const firebaseSnackbar = document.getElementById('firebase-notification-snackbar');
                    firebaseSnackbar.querySelector('#title').textContent = payload.notification.title;
                    firebaseSnackbar.querySelector('#text').textContent = payload.notification.body;
                    ui('#firebase-notification-snackbar');
                });

                // Get the registration token and handle subscription
                getToken(messaging, { vapidKey }).then((currentToken) => {
                    if (currentToken) {
                        const storedToken = localStorage.getItem('firebaseToken');

                        if (storedToken !== currentToken) {
                            fetch('/subscribe-to-topic', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ token: currentToken, topic: 'broadcasts' }),
                            })
                                .then((response) => response.json())
                                .then((data) => {
                                    console.log('Successfully subscribed to topic:', data);
                                    localStorage.setItem('firebaseToken', currentToken); // Store the new token
                                    Notification.requestPermission().then((permission) => {
                                        if (permission === 'granted') {
                                            console.log('Notification permission granted.');
                                        } else {
                                            console.log('Unable to get permission to notify.');
                                        }
                                    });
                                })
                                .catch((error) => {
                                    console.error('Error subscribing to topic:', error);
                                });
                        } else {
                            console.log('Token already subscribed.');
                        }
                    } else {
                        console.log('No registration token available.');
                    }
                }).catch((err) => {
                    console.log('An error occurred while retrieving token: ', err);
                });
            });
        });
    });
} else {
    console.warn('Service workers or notifications are not supported in this browser. Firebase features are disabled.');
}

let installPrompt = null;

function adjustDialogForScreenSize() {
    const infoDialog = document.getElementById('info-dialog');
    const scheduleDialog = document.getElementById('schedule-dialog');
    if (window.innerWidth <= 600) {
        infoDialog.classList.remove('medium-width');
        infoDialog.classList.remove('left');
        infoDialog.classList.add('max');
        scheduleDialog.classList.add('max');
    } else {
        infoDialog.classList.add('medium-width');
        infoDialog.classList.add('left');
        scheduleDialog.classList.remove('max');
        infoDialog.classList.remove('max');
    }
}

async function updateEventCount() {
    const response = await fetch('/get_event_count');
    if (!response.ok) throw new Error('Failed to fetch event count');
    const data = await response.json();
    const broadcastCount = data.broadcast_count;
    const scheduledBroadcastCount = data.scheduled_broadcast_count;

    const eventCount = document.getElementById('event-count');
    let message = "";

    if (broadcastCount >= 1)
        message += `${broadcastCount} active broadcast${broadcastCount > 1 ? "s" : ""}<br>`;
    if (scheduledBroadcastCount >= 1)
        message += `${scheduledBroadcastCount} scheduled broadcast${scheduledBroadcastCount > 1 ? "s" : ""}`;
    if (broadcastCount + scheduledBroadcastCount === 0)
        message = "No broadcasts currently online or events scheduled.";

    const eventStatus = document.getElementById('event-status');
    eventStatus.innerHTML = message;

    if (broadcastCount + scheduledBroadcastCount === 0) {
        eventCount.classList.add('hidden');
        return;
    } else {
        eventCount.classList.remove('hidden');
    }
    eventCount.textContent = broadcastCount + scheduledBroadcastCount;
}

async function showNotification() {
    const response = await fetch('/get_event_count');
    if (!response.ok) throw new Error('Failed to fetch recording status');
    const recordingStatus = await response.json();

    if (recordingStatus.broadcast_count + recordingStatus.scheduled_broadcast_count === 0) {
        return;
    }

    let messages = [];
    let message = "";

    if (recordingStatus.broadcast_count >= 1) {
        const activePhrase = `${recordingStatus.broadcast_count} active broadcast${recordingStatus.broadcast_count > 1 ? "s" : ""}`;
        messages.push(activePhrase);
    }

    if (recordingStatus.scheduled_broadcast_count >= 1) {
        const scheduledPhrase = `${recordingStatus.scheduled_broadcast_count} scheduled broadcast${recordingStatus.scheduled_broadcast_count > 1 ? "s" : ""}`;
        messages.push(scheduledPhrase);
    }

    if (messages.length === 1) {
        message = messages[0];
    } else if (messages.length > 1) {
        message = messages.slice(0, -1).join(", ") + " and " + messages.slice(-1);
    }

    const eventStatus = document.getElementById('event-status');
    eventStatus.innerHTML = message;

    const snackbar = document.getElementById('notification-snackbar');
    snackbar.querySelector('#text').textContent = message;
    ui('#notification-snackbar');
}

async function sendLoveTaps(count) {
    try {
        const response = await fetch("/update-love-taps", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ count }),
        });
    } catch (error) {
    }
}

async function fetchLoveTaps() {
    try {
        const response = await fetch("/fetch-love-taps");
        if (!response.ok) return;
        const data = await response.json();
        const loveCountElem = document.querySelector("#love-count");
        if (loveCountElem) {
            loveCountElem.textContent = `${data.count}`;
        }
    } catch (error) {
    }
}

async function submitSchedule() {
    const host = document.getElementById("schedule-host").value;
    const description = document.getElementById("schedule-description").value;
    const startTime = document.getElementById("date-time-picker").value;
    const speakers = document.getElementById("schedule-speakers").value;
    const duration = document.getElementById("schedule-duration").value;

    if (!host || !description || !startTime || !duration) {
        alert("Please provide all the required fields.");
        return;
    }

    // Send the data to the server
    const response = await fetch("/schedule_broadcast", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ host, description, startTime, speakers, duration })
    });

    if (response.ok) {
        ui("#schedule-dialog");
        description.value = ""; // Clear the description field
        speakers.value = ""; // Clear the speakers field
        startTime.value = ""; // Clear the start time field
        duration.value = ""; // Clear the duration field
    } else {
        ui("#schedule-error");
    }
}

// Add password validation caching
let cachedPasswordValid = false;

async function isCorrectPassword(password) {
    // Return cached result if available
    if (cachedPasswordValid) return true;

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
            cachedPasswordValid = true;
        }
        return result.success;
    } catch (error) {
        return false;
    }
}

async function getSystemInfo() {
    try {
        const response = await fetch('/system-info');
        if (!response.ok) throw new Error('Failed to fetch system info');
        const systemInfo = await response.json();
        const hostNameSpan = document.getElementById('system-info-host');
        hostNameSpan.textContent = systemInfo.hostname;
    } catch (error) {
        console.error('Error fetching system info:', error);
        return null;
    }
}

function checkIfAppInstalled() {
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
    if (isStandalone) {
        const installButton = document.getElementById("install");
        installButton.classList.add("hidden");
    }
}

window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    if (!window.matchMedia('(display-mode: standalone)').matches && !window.navigator.standalone) {
        const installButton = document.getElementById("install");
        installButton.classList.remove("hidden");
    }
});

function disableInAppInstallPrompt() {
    installPrompt = null;
    const installButton = document.getElementById("install");
    installButton.classList.add("hidden");
}

// Event listener for when the app is installed
window.addEventListener("appinstalled", () => {
    disableInAppInstallPrompt();
});

document.addEventListener('DOMContentLoaded', async function () {
    Promise.all([updateEventCount(), showNotification(), fetchLoveTaps()]);
});

document.addEventListener('DOMContentLoaded', function () {
    loadTheme();
    checkIfAppInstalled();

    const installButton = document.getElementById("install");
    installButton.addEventListener("click", async () => {
        if (!installPrompt) {
            console.error("Install prompt is not available.");
            return;
        }
        try {
            const result = await installPrompt.prompt();
            console.log(`Install prompt outcome: ${result.outcome}`);
            if (result.outcome === "accepted") {
                disableInAppInstallPrompt();
            }
        } catch (err) {
            console.error("Error triggering install prompt:", err);
        }
    });

    if (!("beforeinstallprompt" in window)) {
        installButton.classList.add("hidden");
    }

    let lastWidth = window.innerWidth;

    // document.getElementById('toggle-theme').addEventListener('click', toggleMode);

    adjustDialogForScreenSize();

    window.addEventListener('resize', () => {
        const currentWidth = window.innerWidth;
        if (currentWidth !== lastWidth) {
            adjustDialogForScreenSize();
            lastWidth = currentWidth; // Update the last known width
        }
    });

    const loveButton = document.getElementById("love-button");
    let clickCount = 0;
    let timeout = null;
    const debounceTime = 4000; // 4 seconds

    loveButton.addEventListener("click", () => {
        clickCount++;
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            sendLoveTaps(clickCount);
            clickCount = 0;
        }, debounceTime);
    });

    const scheduleBroadcastButton = document.getElementById('schedule-broadcast-button');
    scheduleBroadcastButton.addEventListener('click', async function () {
        const openScheduleDialog = () => {
            ui("#schedule-dialog");
        };

        let password = localStorage.getItem('password');

        if (password && await isCorrectPassword(password)) {
            openScheduleDialog();
            return;
        }

        password = prompt("Please enter your password to schedule an event.");
        if (!password) {
            alert("Password is required to proceed.");
            return;
        }

        if (await isCorrectPassword(password)) {
            localStorage.setItem('password', password);
            openScheduleDialog();
        } else {
            alert("The password is incorrect or not set. Please contact support for assistance.");
        }
    });

    const submitScheduleButton = document.getElementById('submit-schedule-button');
    submitScheduleButton.addEventListener('click', function () {
        submitSchedule();
    });

    flatpickr("#date-time-picker", {
        enableTime: true,
        dateFormat: "Y-m-d H:i",
        altInput: true,
        altFormat: "F j, Y h:i K",
        defaultDate: new Date(),
    });

    setInterval(fetchLoveTaps, 1000 * 60); // Fetch every minute
    const prefetch = (url) => {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = url;
        document.head.appendChild(link);
    };

    document.querySelectorAll('button').forEach(button => {
        button.addEventListener('mouseenter', () => {
            const url = button.getAttribute('onclick')?.match(/'([^']+)'/)?.[1];
            if (url) prefetch(url);
        });
    });
    getSystemInfo();

    const themeButtons = document.querySelectorAll('#theme-button');
    themeButtons.forEach(button => {
        button.addEventListener('click', () => {
            const theme = button.getAttribute('data-color');
            if (theme) {
                ui('theme', theme);
                localStorage.setItem('theme', theme);
            }
        });
    });
    const selectColorInput = document.querySelector("#select-color");
    selectColorInput.addEventListener("change", () => {
        const color = selectColorInput.value;
        ui('theme', color);
        localStorage.setItem('theme', color);
    });

    const modeIcon = document.querySelector("#mode-icon");
    const toggleModeButton = document.querySelector("#toggle-mode");
    if (localStorage.getItem("mode")) {
        toggleModeButton.checked = localStorage.getItem("mode") === "dark";
    } else {
        toggleModeButton.checked = true;
    }
    toggleModeButton.addEventListener("change", () => {
        const newMode = toggleModeButton.checked ? "dark" : "light";
        localStorage.setItem("mode", newMode);
        ui("mode", newMode);
        updateIcon(newMode);
        updateImageSource();
        modeIcon.textContent = toggleModeButton.checked ? "dark_mode" : "light_mode";
    });
    modeIcon.textContent = toggleModeButton.checked ? "dark_mode" : "light_mode";

});
