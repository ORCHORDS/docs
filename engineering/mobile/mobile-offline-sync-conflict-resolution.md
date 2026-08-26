# mobile-offline-sync-conflict-resolution

**Issue:** Resolving data conflicts when an offline mobile client syncs with the server
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When a user edits data offline and another client edits the same record online, a conflict arises on sync. Without a defined strategy, the last write wins silently, losing data.

## Pattern / Solution
**Timestamp-based (last-write-wins):**
```ts
interface Record {
  id: string;
  data: unknown;
  updatedAt: number; // server-authoritative timestamp
  clientUpdatedAt: number; // local edit time
}

function merge(local: Record, server: Record): Record {
  return server.updatedAt > local.clientUpdatedAt ? server : local;
}
```

**Vector clocks (distributed, no single clock):**
```ts
type VectorClock = Record<string, number>;

function happensBefore(a: VectorClock, b: VectorClock): boolean {
  return Object.keys(a).every(k => (a[k] ?? 0) <= (b[k] ?? 0)) &&
    Object.keys(b).some(k => (b[k] ?? 0) > (a[k] ?? 0));
}
```

**Operational transformation (for text/collaborative editing):**
- Use CRDTs (Conflict-free Replicated Data Types) via `yjs` or `automerge`
```ts
import * as Y from 'yjs';
const doc = new Y.Doc();
const text = doc.getText('content');
// Merges automatically without conflicts
```

**Server-side conflict endpoint:**
```http
PUT /api/records/42
If-Match: "etag-from-last-fetch"

→ 200 OK (no conflict)
→ 409 Conflict + { serverVersion, clientVersion } (user must resolve)
```

**UI conflict resolution:**
```tsx
if (conflict) {
  return (
    <ConflictResolver
      local={localVersion}
      server={serverVersion}
      onResolve={(resolved) => {
        saveResolved(resolved);
        clearConflict();
      }}
    />
  );
}
```

## Gotchas
- Timestamps from different devices can't be compared reliably without NTP sync; prefer server-assigned timestamps
- "Last write wins" is acceptable for most user-owned data (profile, settings) but not collaborative or financial data
- CRDTs can grow unbounded; implement periodic compaction/snapshots
- Always store the server version alongside local edits so conflicts can be detected on sync
- Inform users about conflicts rather than silently discarding changes

## Related
- `react-native-offline-first.md`
- `mobile-api-design-patterns.md`
