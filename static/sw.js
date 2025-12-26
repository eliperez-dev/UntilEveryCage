const CACHE_NAME = 'api-cache-v3';
const API_URLS = [
  'https://untileverycage-ikbq.shuttle.app/api/locations',
  'https://untileverycage-ikbq.shuttle.app/api/aphis-reports',
  'https://untileverycage-ikbq.shuttle.app/api/inspection-reports',
  'http://127.0.0.1:8000/api/locations',
  'http://127.0.0.1:8000/api/aphis-reports',
  'http://127.0.0.1:8000/api/inspection-reports',
];

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
  // @ts-ignore
  const { request } = event;
  const url = new URL(request.url);

  // @ts-ignore
  const isApiRequest = API_URLS.some((apiUrl) => url.href.startsWith(apiUrl));

  if (!isApiRequest) {
    return;
  }

  // @ts-ignore
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }

      return fetch(request).then((response) => {
        if (!response || response.status !== 200 || response.type === 'error') {
          return response;
        }

        const responseToCache = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(request, responseToCache);
        });

        return response;
      });
    })
  );
});
