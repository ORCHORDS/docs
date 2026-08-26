# offline-fallback-pages

**Issue:** Users see a browser error page when they are offline instead of a branded offline experience
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The Chrome "No internet" dinosaur appears when a user navigates while offline, with no context about the app.

## Pattern / Solution
```ts
// sw.js
const FALLBACK_URL = '/offline.html';

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open('offline-v1').then(cache => cache.add(FALLBACK_URL))
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(FALLBACK_URL))
    );
  }
});
```

```html
<!-- public/offline.html -->
<!doctype html>
<html>
  <head><title>Offline</title></head>
  <body>
    <h1>You are offline</h1>
    <p>Check your connection and try again.</p>
    <button onclick="location.reload()">Retry</button>
  </body>
</html>
```

## Gotchas
- Workbox GenerateSW plugin configures this automatically with navigateFallback option
- The offline page must be cached during the install event, before any navigation fails
- Background sync API allows queuing failed mutations to retry when connectivity returns

## Related
- `browser-service-worker-cache.md`
- `pwa-manifest-config.md`
