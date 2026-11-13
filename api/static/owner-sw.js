/* Concierge owner alerts.
 * Shows a notification for each push and opens the workspace when it is tapped.
 * It caches nothing and never touches page requests: its only job is alerts. */
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (event) { event.waitUntil(self.clients.claim()); });

self.addEventListener('push', function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; } catch (error) { data = {}; }
  var title = String(data.title || 'New alert from Concierge').slice(0, 100);
  // A browser requires every push to show something, so a malformed payload still shows a generic alert.
  event.waitUntil(self.registration.showNotification(title, {
    body: String(data.body || 'Open your workspace to see it.').slice(0, 200),
    tag: String(data.tag || 'concierge-alert'),
    renotify: true,
    // Visible until dismissed, with a strong vibration: made to be noticed without sound.
    requireInteraction: true,
    vibrate: [250, 120, 250, 120, 250],
    data: { url: '/owner-ui' }
  }));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var target = new URL('/owner-ui', self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (windows) {
    for (var i = 0; i < windows.length; i++) {
      if (windows[i].url.indexOf(self.location.origin + '/owner-ui') === 0 && 'focus' in windows[i]) {
        return windows[i].focus();
      }
    }
    return self.clients.openWindow(target);
  }));
});
