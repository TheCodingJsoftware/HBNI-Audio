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
    const notificationTitle = payload.notification.title;
    const notificationOptions = {
        body: payload.notification.body,
        icon: '/static/icon.png'
    };
    self.registration.showNotification(notificationTitle, notificationOptions);
});