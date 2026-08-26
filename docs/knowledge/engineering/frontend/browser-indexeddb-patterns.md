# browser-indexeddb-patterns

**Issue:** localStorage is synchronous and limited to 5 MB; IndexedDB API is verbose
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Storing large offline datasets or binary blobs in localStorage blocks the main thread and hits quota.

## Pattern / Solution
```ts
// Use the idb library for a promise-based API
import { openDB } from 'idb';

const db = await openDB('myapp', 1, {
  upgrade(db) {
    const store = db.createObjectStore('posts', { keyPath: 'id' });
    store.createIndex('by-date', 'createdAt');
  },
});

// Write
await db.put('posts', { id: 1, title: 'Hello', createdAt: Date.now() });

// Read
const post = await db.get('posts', 1);

// Query by index
const recent = await db.getAllFromIndex('posts', 'by-date', IDBKeyRange.lowerBound(Date.now() - 86400000));
```

## Gotchas
- IndexedDB is transactional; reads and writes in the same transaction are atomic
- Storage quota is typically 60% of available disk space; check with navigator.storage.estimate()
- IndexedDB is not available in some private browsing modes

## Related
- `browser-storage-quota.md`
- `browser-service-worker-cache.md`
