# pwa-service-worker-patterns

**Issue:** Writing and managing service workers for Progressive Web Apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Service workers enable offline support, push notifications, and background sync in PWAs. They run in a separate thread with no DOM access, and their lifecycle (install, activate, fetch) is non-obvious.

## Pattern / Solution
**Register a service worker:**
```ts
// main.ts
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    const registration = await navigator.serviceWorker.register('/sw.js', {
      scope: '/',
      updateViaCache: 'none', // always fetch fresh sw.js
    });
    console.log('SW registered:', registration.scope);
  });
}
```

**Service worker lifecycle:**
```js
// sw.js
const CACHE_NAME = 'v1';

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      cache.addAll(['/index.html', '/app.js', '/styles.css'])
    )
  );
  self.skipWaiting(); // activate immediately
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim(); // take control of existing tabs
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(cached =>
      cached ?? fetch(event.request)
    )
  );
});
```

**Use Workbox (abstracts patterns):**
```js
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { NetworkFirst, CacheFirst, StaleWhileRevalidate } from 'workbox-strategies';

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

registerRoute(({ url }) => url.pathname.startsWith('/api/'), new NetworkFirst({ cacheName: 'api-cache' }));
registerRoute(({ request }) => request.destination === 'image', new CacheFirst({ cacheName: 'image-cache' }));
```

## Gotchas
- Service workers only work over HTTPS (and localhost)
- A new service worker waits until all tabs are closed before activating; `skipWaiting()` + `clients.claim()` overrides this
- `event.waitUntil()` must be called synchronously in the event handler, not inside a Promise chain
- `Cache.match()` does exact URL matching; query strings and fragments matter
- Service worker updates are downloaded in the background; notify users to refresh

## Related
- `pwa-offline-caching-strategies.md`
- `pwa-background-sync.md`
- `pwa-web-push-notifications.md`
