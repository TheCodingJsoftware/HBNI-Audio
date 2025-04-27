importScripts('https://www.gstatic.com/firebasejs/9.2.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.2.0/firebase-messaging-compat.js');

firebase.initializeApp({
    apiKey: "AIzaSyC3G-tsIE9cX-mJzIrZdjuoWpdsiSe8g9M",
    authDomain: "hbni-audio.firebaseapp.com",
    projectId: "hbni-audio",
    storageBucket: "hbni-audio.firebasestorage.app",
    messagingSenderId: "1024721060359",
    appId: "1:1024721060359:web:6761368fb2f863c59da0a2",
    measurementId: "G-JJ6QCL22D6"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function (payload) {
    clients.matchAll({
        type: 'window',
        includeUncontrolled: true
    }).then(function(windowClients) {
        const isAppActive = windowClients.some(client => client.visibilityState === 'visible');
        if (!isAppActive) {
            const notificationTitle = payload.notification.title;
            const notificationOptions = {
                body: payload.notification.body,
                icon: '/static/icon.png',
                data: {
                    link: payload?.data?.link || '/events' // Fallback if no link provided
                }
            };
            // self.registration.showNotification(notificationTitle, notificationOptions);
        }
    });
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    const link = event.notification.data?.link || '/events'; // fallback to /events if no link

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
            // Try to focus an existing window/tab first
            for (const client of windowClients) {
                if (client.url === link && 'focus' in client) {
                    return client.focus();
                }
            }
            // Otherwise open new
            if (clients.openWindow) {
                return clients.openWindow(link);
            }
        })
    );
});
