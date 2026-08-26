# pwa-offline-caching-strategies

**Issue:** Choosing and implementing the right caching strategy in a PWA service worker
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Different resources need different caching strategies. Using cache-first for APIs returns stale data; using network-first for assets wastes bandwidth. Picking the wrong strategy is the most common PWA mistake.

## Pattern / Solution
**Strategy decision matrix:**
| Resource type | Strategy | Rationale |
|---|---|---|
| App shell (HTML, CSS, JS) | Cache first + version | Always fast, update on deploy |
| API data (user feed) | Stale-while-revalidate | Show fast, refresh in background |
| API data (account balance) | Network first | Must be fresh |
| Images / fonts | Cache first, long TTL | Rarely changes |
| CDN assets with hash | Cache first, immutable | Hash = new URL on change |

**Workbox implementations:**
```js
import { registerRoute } from 'workbox-routing';
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { CacheableResponsePlugin } from 'workbox-cacheable-response';

// Images — cache first, expire after 30 days
registerRoute(
  ({ request }) => request.destination === 'image',
  new CacheFirst({
    cacheName: 'images',
    plugins: [
      new ExpirationPlugin({ maxEntries: 60, maxAgeSeconds: 30 * 24 * 60 * 60 }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
);

// API — stale-while-revalidate
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/feed'),
  new StaleWhileRevalidate({ cacheName: 'api-feed' })
);

// Auth endpoints — network only (never cache)
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/auth'),
  new NetworkOnly()
);
```

**Manual cache management:**
```js
// Precache on install
const PRECACHE_URLS = ['/index.html', '/offline.html'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open('v2').then(c => c.addAll(PRECACHE_URLS)));
});

// Serve offline fallback
self.addEventListener('fetch', event => {
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('/offline.html')));
  }
});
```

## Gotchas
- POST requests are not cached by the Cache API; only GET/HEAD
- `CacheableResponsePlugin` with `statuses: [0, 200]` includes opaque responses (cross-origin no-cors) which can be large and corrupt the cache quota
- Browser cache quotas vary (50 MB to several GB); check with `navigator.storage.estimate()`
- `StaleWhileRevalidate` always makes a network request in the background — not truly offline-capable for that resource
- Cached responses don't inherit CORS headers; be explicit about cross-origin caching

## Related
- `pwa-service-worker-patterns.md`
- `pwa-background-sync.md`
- `mobile-image-caching-patterns.md`
