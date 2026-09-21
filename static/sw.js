// Public API responses must not be cached client-side. A cached response can
// outlive a privacy suppression and become an alternate disclosure path.
const CACHE_NAME = 'api-cache-v6';

// @ts-ignore
self.addEventListener('install', (event) => {
  // @ts-ignore
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // @ts-ignore
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      // @ts-ignore
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  // @ts-ignore
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Deliberately do not intercept API requests. The legacy application and
  // V2 routes must always reach the current server-side suppression gates.
});
