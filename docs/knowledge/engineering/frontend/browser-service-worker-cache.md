# browser-service-worker-cache

**Issue:** App fails to load offline; repeated network requests for static assets waste bandwidth
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users on flaky connections see blank screens; static JS and CSS are re-downloaded on every visit.

## Pattern / Solution
```ts
// sw.js - Cache First for static assets
const CACHE_NAME = 'app-v1';
const STATIC_ASSETS = ['/app.js', '/app.css', '/offline.html'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then(cached => {
      return cached ?? fetch(e.request).then(response => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        return response;
      });
    }).catch(() => caches.match('/offline.html'))
  );
});
```

## Gotchas
- Service workers only work on HTTPS (except localhost)
- Cache versioning is critical; stale caches must be explicitly deleted on activate
- Workbox simplifies this significantly with generateSW and injectManifest modes

## Related
- `browser-indexeddb-patterns.md`
- `offline-fallback-pages.md`
