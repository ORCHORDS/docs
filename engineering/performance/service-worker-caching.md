# Service Worker Caching Strategies

Service workers enable powerful caching strategies that significantly improve web application performance and offline capabilities. These strategies determine how resources are fetched, stored, and served to users.

## Cache-First Strategy

The cache-first approach serves cached content immediately while updating it in the background. This strategy works well for static assets like images, CSS, and JavaScript files that don't change frequently.

```javascript
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) return response;
        return fetch(event.request);
      })
  );
});
```

## Network-First Strategy

Network-first retrieves resources from the network first, falling back to cache only if the network fails. This ensures users always get the most recent content.

```javascript
self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache successful responses
        caches.open('my-cache').then(cache => {
          cache.put(event.request, response.clone());
        });
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
```

## Stale-While-Revalidate

This strategy serves cached content immediately while simultaneously fetching fresh data. It provides immediate responses with eventual consistency.

```javascript
self.addEventListener('fetch', event => {
  const cacheName = 'my-cache';

  event.respondWith(
    caches.match(event.request).then(response => {
      const fetchPromise = fetch(event.request).then(networkResponse => {
        caches.open(cacheName).then(cache => {
          cache.put(event.request, networkResponse.clone());
        });
        return networkResponse;
      });

      return response || fetchPromise;
    })
  );
});
```

## Runtime Caching

Runtime caching dynamically caches requests based on conditions during execution. This approach handles complex scenarios where caching decisions are made at runtime.

```javascript
self.addEventListener('fetch', event => {
  if (event.request.url.includes('/api/')) {
    // API calls go to network first with cache fallback
    event.respondWith(
      fetch(event.request)
        .then(response => {
          caches.open('api-cache').then(cache => {
            cache.put(event.request, response.clone());
          });
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  }
});
```

## Precaching

Precaching involves caching resources during service worker installation. This ensures all critical assets are available offline immediately.

```javascript
const PRECACHE_URLS = [
  '/',
  '/styles/main.css',
  '/scripts/main.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open('my-precache').then(cache => {
      return cache.addAll(PRECACHE_URLS);
    })
  );
});
```

## Cache Invalidation

Cache invalidation removes outdated cached content to prevent serving stale resources. This is crucial for
