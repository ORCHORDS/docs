# service-worker-cache-strategy

**Issue:** Assets re-fetch from network on every visit despite Service Worker being registered
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Service Workers intercept fetch events and can serve from cache. Poor strategy selection causes unnecessary network requests or stale content.

## Pattern / Solution
1. Cache-First: serve from cache; fall back to network. Use for static assets.\n2. Network-First: try network; fall back to cache. Use for HTML and API responses.\n3. Stale-While-Revalidate: serve from cache immediately; update cache in background.\n4. Use Workbox to implement strategies with minimal boilerplate.\n5. Precache critical assets during install event; runtime-cache the rest.

## Gotchas
- Service Workers are scope-limited; a SW at /app/sw.js only controls /app/*.\n- Updating a SW requires all controlled tabs to close; use skipWaiting + clients.claim cautiously.\n- Cache storage is not infinite; implement cache size limits and eviction policies.

## Related
cache-control-headers, cdn-cache-strategy, above-fold-optimization
