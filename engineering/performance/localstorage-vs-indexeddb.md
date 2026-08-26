# localstorage-vs-indexeddb

**Issue:** Wrong storage API chosen for the use case
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
localStorage is synchronous and limited to 5-10 MB. Reading large values from it blocks the main thread. IndexedDB is async, supports large data, and is the right choice for anything beyond small key-value pairs.

## Pattern / Solution
1. Use localStorage only for: small (< 100 KB) user preferences, feature flags, session tokens.\n2. Use IndexedDB for: offline data, large datasets, structured data, binary data.\n3. Use sessionStorage as an in-memory alternative that clears on tab close.\n4. Use Cache API (via Service Worker) for HTTP response caching.\n5. Use cookies only for data that must be sent to the server.

## Gotchas
- localStorage.getItem on a 5 MB value blocks the main thread measurably.\n- localStorage is synchronous and cannot be used from Web Workers.\n- Third-party iframes share localStorage with the origin; be aware of data leakage.

## Related
indexeddb-performance, service-worker-cache-strategy, memory-management-js
