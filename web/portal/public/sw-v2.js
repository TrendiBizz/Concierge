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

  if (event.request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const response = await fetch(event.request, {cache: 'no-store'});
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put('/studio/', copy)).catch(() => undefined);
        return response;
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
