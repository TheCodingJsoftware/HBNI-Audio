import { loadTheme, toggleMode } from "/static/js/theme.js";
import "flatpickr";
require("flatpickr/dist/themes/dark.css");

let fetchInterval = null;

function shareUpcomingBroadcast(text) {
    // Check if the Web Share API is available
    if (navigator.share) {
        const url = window.location.origin + "/events";
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
        navigator.clipboard.writeText(`${text}\n\nVisit here: ${window.location.origin}/events`)
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
    navigator.clipboard.writeText(`${text}\n\nVisit here: ${window.location.origin}/events`);
    ui("#copied-to-clipboard");
}

async function updateRecordingStatus() {
    const response = await fetch('/get_recording_status');
    if (!response.ok) throw new Error('Failed to fetch recording status');
    const recordingStatus = await response.json();

    for (let [host, recordingStatusData] of Object.entries(recordingStatus)) {
        host = host.replace("/", "")
        const recordingStatusElement = document.getElementById(`recording-status-${host}`);
        if (recordingStatusElement){
            recordingStatusElement.classList.remove('hidden');
        }
    }
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

async function isCorrectPassword(password) {
    try {
        const response = await fetch("/validate-password", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ password })
        });

        const result = await response.json();
        return result.success;
    } catch (error) {
        return false;
    }
}

async function editSchedule(scheduleId) {
    const response = await fetch(`/get_schedule/${scheduleId}`);
    if (!response.ok) throw new Error('Failed to fetch schedule data');
    const data = await response.json();

    document.getElementById("schedule-host").value = data.host;
    document.getElementById("schedule-description").value = data.description;
    document.getElementById("date-time-picker").value = data.start_time;
    document.getElementById("schedule-speakers").value = data.speakers;
    document.getElementById("schedule-duration").value = data.duration;

    const submitScheduleButton = document.getElementById('submit-schedule-button');
    submitScheduleButton.addEventListener('click', function () {
        submitEditedSchedule(scheduleId);
    });

    const deleteScheduleButton = document.getElementById('delete-schedule-button');
    deleteScheduleButton.addEventListener('click', function () {
        deleteSchedule(scheduleId);
    });

    ui("#edit-schedule-dialog");
}

async function submitEditedSchedule(scheduleId) {
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
    const response = await fetch(`/edit_schedule/${scheduleId}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ host, description, startTime, speakers, duration })
    });

    if (response.ok) {
        ui("#edit-schedule-dialog");
        ui("#edit-schedule-success");
    } else {
        ui("#edit-schedule-error");
    }
}

async function deleteSchedule(scheduleId) {
    const response = await fetch(`/edit_schedule/${scheduleId}`, {
        method: "DELETE"
    });

    if (response.ok) {
        ui("#edit-schedule-dialog");
        ui("#edit-schedule-success");
    } else {
        ui("#edit-schedule-error");
    }
}

// Periodically fetch updates
document.addEventListener('DOMContentLoaded', async function () {
    loadTheme();
    const shouldShowEditButton = await isCorrectPassword(localStorage.getItem('password') || '') || false;
    document.getElementById('toggle-theme').addEventListener('click', toggleMode);
    document.querySelectorAll('audio').forEach(audioElement => {
        audioElement.onerror = function () {
            alert('The audio stream is unavailable because it is served over an insecure connection. Please contact support for assistance.');
        };
    });

    const scheduledBroadcastsContainer = document.getElementById('scheduled-broadcasts-container');
    if (scheduledBroadcastsContainer) { // There might not be any scheduled broadcasts
        scheduledBroadcastsContainer.querySelectorAll('[id^=\'article\']').forEach(article => {
            const scheduleId = article.getAttribute('data-id');
            const host = article.getAttribute('data-host');
            const scheduledDescription = article.querySelector(`#scheduled-description-${scheduleId}`);
            const copyMessage = scheduledDescription.textContent;

            const shareButton = article.querySelector(`#share-button`);
            const copyButton = article.querySelector(`#copy-button`);
            const editButton = article.querySelector(`#edit-button`);
            if (shouldShowEditButton){
                editButton.classList.remove('hidden');
            }

            editButton.addEventListener('click', function () {
                editSchedule(scheduleId);
            });
            shareButton.addEventListener('click', function () {
                shareUpcomingBroadcast(copyMessage);
            });
            copyButton.addEventListener('click', function () {
                copyUpcomingBroadcastToClipboard(copyMessage);
            });
        });
    }
    const broadcastsContainer = document.getElementById('broadcasts-container');
    if (broadcastsContainer) { // There might not be any broadcasts live
        broadcastsContainer.querySelectorAll('[id^=\'article\']').forEach(article => {
            const title = article.getAttribute('data-title');
            const description = article.getAttribute('data-description');

            const copyMessage = `${title} started a broadcast with the description: "${description}".`;

            const shareButton = article.querySelector(`#share-button`);
            const copyButton = article.querySelector(`#copy-button`);
            shareButton.addEventListener('click', function () {
                shareUpcomingBroadcast(copyMessage);
            });
            copyButton.addEventListener('click', function () {
                copyUpcomingBroadcastToClipboard(copyMessage);
            });
        });
    }

    flatpickr("#date-time-picker", {
        enableTime: true,
        dateFormat: "Y-m-d H:i",
        altInput: true,
        altFormat: "F j, Y H:i",
        defaultDate: new Date(),
    });

    try {
        const response = await fetch('/get_broadcast_data');
        if (!response.ok) throw new Error('Failed to fetch broadcast stats');
        const broadcast_data = await response.json();

        if (broadcast_data && broadcast_data.length > 0) {
            fetchInterval = setInterval(fetchBroadcastData, 1000 * 60); // Update every minute
        }
        await updateRecordingStatus();
    } catch (error) {
        console.error('Error during initial fetch:', error);
    }
});