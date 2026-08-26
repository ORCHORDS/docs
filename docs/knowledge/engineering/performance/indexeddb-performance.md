# indexeddb-performance

**Issue:** IndexedDB operations are slow or blocking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
IndexedDB is async but can be slow due to poor index design, large transactions, or excessive reads. It is the recommended offline storage for large datasets.

## Pattern / Solution
1. Create indexes on frequently queried fields; avoid full-table scans.\n2. Batch writes in a single transaction for 10-100x throughput improvement.\n3. Use getAll instead of multiple get calls.\n4. Keep transactions short; long transactions block other reads/writes.\n5. Use idb or Dexie.js wrappers for cleaner Promise-based API.

## Gotchas
- IndexedDB is unavailable in private browsing mode in some browsers.\n- Schema migrations via onupgradeneeded must be backward-compatible.\n- iOS Safari has a 50 MB quota limit for IndexedDB; plan for quota exceeded errors.

## Related
localstorage-vs-indexeddb, memory-management-js, service-worker-cache-strategy
