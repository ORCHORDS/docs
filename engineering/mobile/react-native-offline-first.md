# react-native-offline-first

**Issue:** Building React Native apps that work without a network connection
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mobile apps frequently encounter poor or no connectivity. An offline-first architecture caches data locally and syncs when the connection returns, instead of failing or showing error screens.

## Pattern / Solution
**Detect network state:**
```tsx
import NetInfo from '@react-native-community/netinfo';

const unsubscribe = NetInfo.addEventListener(state => {
  const isOnline = state.isConnected && state.isInternetReachable;
  store.dispatch(setNetworkStatus(isOnline));
});
```

**Local persistence with WatermelonDB (large datasets):**
```ts
import { Database } from '@nozbe/watermelondb';
import SQLiteAdapter from '@nozbe/watermelondb/adapters/sqlite';

const adapter = new SQLiteAdapter({ schema, migrations });
const database = new Database({ adapter, modelClasses: [Post, Comment] });

// Query locally, sync in background
await database.write(async () => {
  await database.get('posts').create(post => {
    post.title = 'Hello';
    post._raw.synced = false;
  });
});
```

**Simpler: MMKV + React Query:**
```ts
import { MMKV } from 'react-native-mmkv';
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { persistQueryClient } from '@tanstack/react-query-persist-client';

const storage = new MMKV();
const persister = createSyncStoragePersister({
  storage: { getItem: k => storage.getString(k) ?? null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) },
});
persistQueryClient({ queryClient, persister, maxAge: 1000 * 60 * 60 * 24 });
```

**Queue mutations for later:**
```ts
// Simple outbox pattern
async function queuedMutation(payload: unknown) {
  const queue = JSON.parse(storage.getString('mutation_queue') ?? '[]');
  queue.push({ payload, timestamp: Date.now() });
  storage.set('mutation_queue', JSON.stringify(queue));
  if (isOnline) await flushQueue();
}
```

## Gotchas
- `isInternetReachable` can be `null` on Android during boot; treat null as offline
- SQLite on Hermes requires the `op-sqlite` or `react-native-quick-sqlite` package, not the legacy `react-native-sqlite-storage`
- WatermelonDB's sync protocol requires a specific server-side API contract (pull/push endpoints)
- Optimistic UI updates need rollback logic when the queued mutation eventually fails
- Large MMKV values (>1 MB) should be chunked; MMKV is not designed for binary blobs

## Related
- `mobile-offline-sync-conflict-resolution.md`
- `react-native-performance-optimization.md`
- `mobile-api-design-patterns.md`
