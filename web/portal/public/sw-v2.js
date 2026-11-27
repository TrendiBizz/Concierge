/* Concierge studio shell (v2).
 *
 * Why a new filename: v1 was cached by Cloudflare and by the browser as an opaque resource with
 * no Cache-Control at all, and its cache name was the constant 'concierge-studio-v1', so nothing
 * ever invalidated it. Hard refresh did not help either, because the worker answered the
 * navigation from its own cache when the network hiccuped during a deploy — the owner sat on a
 * stale build while the server served the new one.
 *
 * Rules now:
 *   - the cache name carries the build id, stamped at deploy time, so a new build is a new cache
 *   - a navigation is always network-first with no-store, and the cached shell is used ONLY when
 *     the browser is offline
 *   - hashed assets stay cache-first (content-addressed names cannot go stale)
 */
const CACHE = 'concierge-studio-__BUILD__';

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/owner/') || url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/')) return;
  if (url.pathname === '/studio/install' || url.pathname === '/studio/install/') return;

  if (event.request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        // Fetch by URL string rather than passing the navigate Request with init overrides:
        // WebKit/iOS Safari throws TypeError on Request-with-init for navigate requests,
        // which left iPhones on a blank page.
        const response = await fetch(event.request.url, {cache: 'no-store', credentials: 'same-origin'});
        const clean = response.redirected
          ? new Response(response.body, {status: response.status, statusText: response.statusText, headers: response.headers})
          : response;
        if (clean.status === 200 && (url.pathname === '/studio/' || url.pathname === '/studio')) {
          const copy = clean.clone();
          caches.open(CACHE).then((cache) => cache.put('/studio/', copy)).catch(() => undefined);
        }
        return clean;
      } catch (error) {
        if (self.navigator && self.navigator.onLine === false) {
          const hit = await caches.match('/studio/');
          if (hit) return hit;
        }
        throw error;
      }
    })());
    return;
  }

  if (url.pathname.startsWith('/studio/assets/')) {
    event.respondWith((async () => {
      const hit = await caches.match(event.request);
      if (hit) return hit;
      const response = await fetch(event.request);
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy)).catch(() => undefined);
      }
      return response;
    })());
  }
});

/* Alerts (Web Push). Owner alerts arrive here even when the Studio is closed. A browser requires every
 * push to show something, so a malformed payload still shows a generic alert. */
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (error) { data = {}; }
  event.waitUntil(self.registration.showNotification(String(data.title || 'New alert from Concierge').slice(0, 100), {
    body: String(data.body || 'Open your inbox to see it.').slice(0, 200),
    tag: String(data.tag || 'concierge-alert'),
    renotify: true,
    vibrate: [250, 120, 250],
    data: {url: '/studio/'},
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
    for (const client of windows) {
      if (client.url.includes('/studio') && 'focus' in client) return client.focus();
    }
    return self.clients.openWindow('/studio/');
  })());
});
