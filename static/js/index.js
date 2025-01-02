import { loadTheme, toggleMode } from "/static/js/theme.js";

function adjustDialogForScreenSize() {
    const infoDialog = document.getElementById('info-dialog');
    const downloadDialog = document.getElementById('download-dialog');
    if (window.innerWidth <= 600) {
        infoDialog.classList.add('max');
        downloadDialog.classList.add('bottom');
    } else {
        downloadDialog.classList.remove('bottom');
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
    const eventTooltipStatus = document.getElementById('event-tooltip-status');
    let message = "";

    if (broadcastCount >= 1)
        message += `${broadcastCount} active broadcast${broadcastCount > 1 ? "s" : ""}<br>`;
    if (scheduledBroadcastCount >= 1)
        message += `${scheduledBroadcastCount} scheduled broadcast${scheduledBroadcastCount > 1 ? "s" : ""}`;
    if (broadcastCount + scheduledBroadcastCount === 0)
        message = "No broadcasts currently<br>online or events schedulded.";

    eventTooltipStatus.innerHTML = message;

    if (broadcastCount + scheduledBroadcastCount === 0) {
        eventCount.classList.add('hidden');
        return;
    }else{
        eventCount.classList.remove('hidden');
    }
    eventCount.textContent = broadcastCount + scheduledBroadcastCount;
}

async function showNotification() {
    const response = await fetch('/get_event_count');
    if (!response.ok) throw new Error('Failed to fetch recording status');
    const recordingStatus = await response.json();

    if (recordingStatus.broadcast_count + recordingStatus.scheduled_broadcast_count === 0) {
        ui("#no-broadcasts-or-events-scheduled");
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

    const snackbar = document.getElementById('notification-snackbar');
    snackbar.querySelector('#text').textContent = message;
    ui('#notification-snackbar');
}

document.addEventListener('DOMContentLoaded', async function () {
    Promise.all([updateEventCount(), showNotification()]);
});

document.addEventListener('DOMContentLoaded', function () {
    loadTheme();

    let lastWidth = window.innerWidth;

    document.getElementById('toggle-theme').addEventListener('click', toggleMode);

    adjustDialogForScreenSize();

    window.addEventListener('resize', () => {
        const currentWidth = window.innerWidth;
        if (currentWidth !== lastWidth) {
            adjustDialogForScreenSize();
            lastWidth = currentWidth; // Update the last known width
        }
    });
});
