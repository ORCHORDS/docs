# browser-storage-quota

**Issue:** Storage fills up silently, causing IndexedDB writes to fail without clear errors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An offline-first app stops syncing because IndexedDB throws QuotaExceededError with no user-facing message.

## Pattern / Solution
```ts
// Check available storage
const estimate = await navigator.storage.estimate();
const usedMB = ((estimate.usage ?? 0) / 1024 / 1024).toFixed(1);
const quotaMB = ((estimate.quota ?? 0) / 1024 / 1024).toFixed(0);
console.log(`Using ${usedMB} MB of ${quotaMB} MB`);

// Request persistent storage to prevent eviction
const isPersisted = await navigator.storage.persisted();
if (!isPersisted) {
  const granted = await navigator.storage.persist();
  console.log('Persistent storage granted:', granted);
}

// Eviction policy: LRU by origin; persistent storage is never evicted
```

## Gotchas
- Best-effort storage can be evicted by the browser under memory pressure
- navigator.storage.persist() may be auto-granted if the site is installed as PWA or bookmarked
- iOS Safari has historically lower storage quotas than Chrome/Firefox

## Related
- `browser-indexeddb-patterns.md`
- `pwa-manifest-config.md`
