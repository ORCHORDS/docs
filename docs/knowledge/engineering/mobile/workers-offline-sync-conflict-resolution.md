# Offline Sync Conflict Resolution API in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your mobile app supports offline editing. When a user edits data offline and reconnects, the server may have received conflicting writes from another device or another user. You need a sync API in Cloudflare Workers that detects conflicts using vector clocks, performs a three-way merge for structured records, and returns a conflict delta to the client so it can update its local view without losing acknowledged writes.

## Context

Last-write-wins (LWW) based on wall-clock time is unreliable: mobile device clocks drift by seconds to minutes, and NTP sync is not guaranteed on reconnect. Vector clocks give a causal ordering over writes: if clock A dominates B (A[k] ≥ B[k] for all k, strictly greater for at least one), A causally follows B. If neither dominates, the writes are concurrent and a merge is needed.

The sync flow: client sends a change log (list of field mutations since last sync) with its current vector clock. The server compares the client clock against the stored server clock. If client dominates, the write is applied. If server dominates, the client is behind and must pull the server state. If concurrent, a three-way merge is attempted using the common ancestor stored in D1, and the result is returned with a conflict delta.

D1 stores the current resolved state, the server vector clock, and the last common ancestor per record. Durable Objects are the right choice for high-contention records; D1 is appropriate when write frequency per record is low (< 1 write/second per record).

## Solution

```typescript
export interface Env {
  DB: D1Database;
}

// --- Vector clock primitives ---

type VectorClock = Record<string, number>;

function vcDominates(a: VectorClock, b: VectorClock): boolean {
  // Returns true if a is causally after b (a >= b element-wise, strictly > in at least one)
  const allKeys = new Set([...Object.keys(a), ...Object.keys(b)]);
  let strictlyGreater = false;
  for (const k of allKeys) {
    const av = a[k] ?? 0;
    const bv = b[k] ?? 0;
    if (av < bv) return false;
    if (av > bv) strictlyGreater = true;
  }
  return strictlyGreater;
}

function vcEqual(a: VectorClock, b: VectorClock): boolean {
  const allKeys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of allKeys) {
    if ((a[k] ?? 0) !== (b[k] ?? 0)) return false;
  }
  return true;
}

function vcMerge(a: VectorClock, b: VectorClock): VectorClock {
  const result: VectorClock = { ...a };
  for (const [k, v] of Object.entries(b)) {
    result[k] = Math.max(result[k] ?? 0, v);
  }
  return result;
}

function vcIncrement(clock: VectorClock, node: string): VectorClock {
  return { ...clock, [node]: (clock[node] ?? 0) + 1 };
}

// --- Change log types ---

interface FieldChange {
  field: string;
  old_value: unknown;  // Value client had before editing (for ancestor comparison)
  new_value: unknown;  // Value client wants to write
}

interface LocalChange {
  record_id: string;
  table_name: string;
  device_id: string;
  client_clock: VectorClock;
  changes: FieldChange[];
  changed_at: string;  // ISO8601, informational only
}

interface SyncResult {
  record_id: string;
  status: 'applied' | 'merged' | 'conflict' | 'rejected';
  server_clock: VectorClock;
  resolved_data: Record<string, unknown>;
  conflicts: ConflictDelta[];
}

interface ConflictDelta {
  record_id: string;
  field: string;
  client_value: unknown;
  server_value: unknown;
  resolved_value: unknown;
  resolution: 'client_wins' | 'server_wins' | 'merged';
}

// --- D1 row type ---

interface SyncRow {
  id: string;
  table_name: string;
  data: string;           // JSON
  server_clock: string;   // JSON VectorClock
  ancestor_data: string | null;  // JSON, previous server state before last write
  updated_at: string;
}

// --- Three-way merge ---
// ancestor: common base state
// server: current server state (may have changed since client last synced)
// clientChanges: what the client wants to apply

function threeWayMerge(
  ancestor: Record<string, unknown>,
  server: Record<string, unknown>,
  clientChanges: FieldChange[],
  recordId: string,
): { merged: Record<string, unknown>; deltas: ConflictDelta[] } {
  const merged = { ...server };
  const deltas: ConflictDelta[] = [];

  for (const change of clientChanges) {
    const { field, old_value, new_value } = change;
    const ancestorValue = ancestor[field];
    const serverValue = server[field];

    const clientChanged =
      JSON.stringify(new_value) !== JSON.stringify(old_value);
    const serverChanged =
      JSON.stringify(serverValue) !== JSON.stringify(ancestorValue);

    if (!clientChanged) {
      // Client did not modify this field; keep server value as-is
      continue;
    }

    if (!serverChanged) {
      // Only client modified it; apply client value
      merged[field] = new_value;
      deltas.push({
        record_id: recordId,
        field,
        client_value: new_value,
        server_value: serverValue,
        resolved_value: new_value,
        resolution: 'client_wins',
      });
      continue;
    }

    // Both client and server modified this field concurrently
    if (
      typeof new_value === 'number' &&
      typeof serverValue === 'number' &&
      typeof ancestorValue === 'number'
    ) {
      // Additive merge: apply client's numeric delta on top of server value
      const clientDelta = new_value - ancestorValue;
      const mergedValue = serverValue + clientDelta;
      merged[field] = mergedValue;
      deltas.push({
        record_id: recordId,
        field,
        client_value: new_value,
        server_value: serverValue,
        resolved_value: mergedValue,
        resolution: 'merged',
      });
    } else {
      // Non-numeric concurrent conflict: server wins (LWW fallback)
      merged[field] = serverValue;
      deltas.push({
        record_id: recordId,
        field,
        client_value: new_value,
        server_value: serverValue,
        resolved_value: serverValue,
        resolution: 'server_wins',
      });
    }
  }

  return { merged, deltas };
}

// --- Apply a single local change ---

async function applyChange(change: LocalChange, env: Env): Promise<SyncResult> {
  const existing = await env.DB.prepare(
    'SELECT * FROM sync_records WHERE id = ? AND table_name = ?',
  ).bind(change.record_id, change.table_name).first<SyncRow>();

  const serverClock: VectorClock = existing ? JSON.parse(existing.server_clock) : {};
  const serverData: Record<string, unknown> = existing ? JSON.parse(existing.data) : {};
  const ancestorData: Record<string, unknown> = existing?.ancestor_data
    ? JSON.parse(existing.ancestor_data)
    : serverData;

  const clientClock = change.client_clock;

  let resolvedData: Record<string, unknown>;
  let status: SyncResult['status'];
  let deltas: ConflictDelta[] = [];

  if (!existing) {
    // New record — apply client state directly
    resolvedData = Object.fromEntries(
      change.changes.map((c) => [c.field, c.new_value]),
    );
    status = 'applied';
  } else if (vcDominates(clientClock, serverClock) || vcEqual(clientClock, serverClock)) {
    // Client is at or ahead of server — fast-path apply
    resolvedData = { ...serverData };
    for (const c of change.changes) {
      resolvedData[c.field] = c.new_value;
    }
    status = 'applied';
  } else if (vcDominates(serverClock, clientClock)) {
    // Server strictly ahead — client is stale; reject and return current state
    resolvedData = serverData;
    status = 'rejected';
    deltas = change.changes.map((c) => ({
      record_id: change.record_id,
      field: c.field,
      client_value: c.new_value,
      server_value: serverData[c.field],
      resolved_value: serverData[c.field],
      resolution: 'server_wins',
    }));
  } else {
    // Concurrent — three-way merge
    const result = threeWayMerge(ancestorData, serverData, change.changes, change.record_id);
    resolvedData = result.merged;
    deltas = result.deltas;
    status = deltas.some((d) => d.resolution === 'server_wins') ? 'conflict' : 'merged';
  }

  // Advance vector clock and persist
  const newClock = vcIncrement(vcMerge(serverClock, clientClock), 'server');
  const now = new Date().toISOString();

  if (existing) {
    await env.DB.prepare(
      `UPDATE sync_records
       SET data = ?, server_clock = ?, ancestor_data = ?, updated_at = ?
       WHERE id = ? AND table_name = ?`,
    ).bind(
      JSON.stringify(resolvedData),
      JSON.stringify(newClock),
      JSON.stringify(serverData),  // previous server state becomes new common ancestor
      now,
      change.record_id,
      change.table_name,
    ).run();
  } else {
    await env.DB.prepare(
      `INSERT INTO sync_records (id, table_name, data, server_clock, ancestor_data, updated_at)
       VALUES (?, ?, ?, ?, NULL, ?)`,
    ).bind(
      change.record_id,
      change.table_name,
      JSON.stringify(resolvedData),
      JSON.stringify(newClock),
      now,
    ).run();
  }

  return {
    record_id: change.record_id,
    status,
    server_clock: newClock,
    resolved_data: resolvedData,
    conflicts: deltas,
  };
}

// --- Main fetch handler ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /sync — accept a batch of local changes
    if (request.method === 'POST' && url.pathname === '/sync') {
      const { changes } = await request.json<{ changes: LocalChange[] }>();

      if (!Array.isArray(changes) || changes.length === 0) {
        return Response.json(
          { error: 'changes must be a non-empty array' },
          { status: 400 },
        );
      }

      if (changes.length > 100) {
        return Response.json(
          { error: 'Maximum 100 changes per sync batch' },
          { status: 422 },
        );
      }

      // Process sequentially to avoid intra-batch write conflicts on the same record
      const results: SyncResult[] = [];
      for (const change of changes) {
        results.push(await applyChange(change, env));
      }

      return Response.json({
        results,
        has_conflicts: results.some((r) => r.status === 'conflict'),
        has_rejections: results.some((r) => r.status === 'rejected'),
        synced_at: new Date().toISOString(),
      });
    }

    // GET /sync/:table/:id — fetch current server state and clock for a record
    if (request.method === 'GET') {
      const match = url.pathname.match(/^\/sync\/([^/]+)\/([^/]+)$/);
      if (match) {
        const [, tableName, recordId] = match;
        const row = await env.DB.prepare(
          'SELECT * FROM sync_records WHERE id = ? AND table_name = ?',
        ).bind(recordId, tableName).first<SyncRow>();

        if (!row) return Response.json({ found: false });
        return Response.json({
          found: true,
          data: JSON.parse(row.data),
          server_clock: JSON.parse(row.server_clock),
          updated_at: row.updated_at,
        });
      }
    }

    // GET /sync/:table?since= — incremental sync (pull records changed since timestamp)
    if (request.method === 'GET' && url.pathname.match(/^\/sync\/[^/]+$/)) {
      const tableName = url.pathname.split('/').pop()!;
      const since = url.searchParams.get('since') ?? '1970-01-01T00:00:00Z';
      const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '50', 10), 200);

      const { results } = await env.DB.prepare(
        'SELECT id, data, server_clock, updated_at FROM sync_records WHERE table_name = ? AND updated_at > ? ORDER BY updated_at ASC LIMIT ?',
      ).bind(tableName, since, limit).all<Omit<SyncRow, 'ancestor_data' | 'table_name'>>();

      return Response.json({
        records: results.map((r) => ({
          id: r.id,
          data: JSON.parse(r.data),
          server_clock: JSON.parse(r.server_clock),
          updated_at: r.updated_at,
        })),
        count: results.length,
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Implementation Details

**D1 schema:**

```sql
CREATE TABLE sync_records (
  id            TEXT NOT NULL,
  table_name    TEXT NOT NULL,
  data          TEXT NOT NULL,          -- JSON: current resolved state
  server_clock  TEXT NOT NULL,          -- JSON: VectorClock
  ancestor_data TEXT,                   -- JSON: state before last merge (for 3-way merge)
  updated_at    TEXT NOT NULL,
  PRIMARY KEY (id, table_name)
);
CREATE INDEX idx_sync_updated ON sync_records (table_name, updated_at);
```

**Vector clock interpretation:**
- `{ "device-A": 3, "server": 1 }` — device A has made 3 writes; the server has committed 1 write since the last full sync.
- The client increments its own device counter locally before adding a change to the local change log.
- The server increments the `"server"` counter on every accepted or merged write, providing a monotonic progress signal for incremental pull.

**Three-way merge strategy by field type:**

| Both changed | Field type | Resolution |
|---|---|---|
| Only client | any | client_wins |
| Only server | any | server_wins |
| Concurrent | numeric | additive delta merge |
| Concurrent | string / boolean / object | server_wins (LWW fallback) |

Customize per table by passing a merge strategy map to `threeWayMerge`.

**Incremental pull (`/sync/:table?since=`):** After pushing local changes, the client pulls records updated since its last sync timestamp. The server returns them sorted by `updated_at` ascending so the client can set its next `since` to the `updated_at` of the last record received.

**Durable Objects for high-contention records:** D1 does not support row-level locking. For records with > 1 write/second (e.g., a shared document edited by a team), route all writes through a Durable Object that holds the vector clock in memory and persists to D1 on a debounced interval.

## Anti-patterns

- Using wall-clock `Date.now()` for conflict resolution — clocks drift on mobile devices; a client with a clock 30 seconds ahead will always win LWW races regardless of actual edit order.
- Processing the change batch in parallel with `Promise.all` — concurrent writes to the same `record_id` within a batch will produce a race on the D1 row; process sequentially.
- Not storing `ancestor_data` — without a common ancestor, a three-way merge cannot determine which side changed a field; you must fall back to LWW on every concurrent write.
- Returning only the resolved state without conflict deltas — the client needs to know which of its pending writes were overridden to update the local UI correctly.

## Gotchas

- Vector clocks grow as new device IDs are added. Prune device entries that have not written in > 90 days using a Cron Trigger Worker that sets their counter to 0 or removes them from the clock JSON.
- When a user resets the app (clear data / reinstall), the app must generate a new `device_id`. Reusing an old device ID after a reset means the new clock will dominate the server clock for stale data, overwriting server edits made since the reset.
- The `ancestor_data` column holds the state before the most recent write. For long offline periods spanning many server-side merges, the stored ancestor may be too old to produce a useful three-way merge. In this case, fall back to server-wins and notify the client to pull the full server state.
- D1 `updated_at` is stored as a plain ISO8601 string and compared lexicographically in the incremental pull query. Ensure all dates are zero-padded UTC strings (`new Date().toISOString()` guarantees this in JavaScript).

## Verification

```bash
# Initial write from device-A
curl -s -X POST https://your-worker.workers.dev/sync \
  -H "Content-Type: application/json" \
  -d '{
    "changes": [{
      "record_id": "note-1",
      "table_name": "notes",
      "device_id": "device-A",
      "client_clock": {"device-A": 1},
      "changes": [{"field": "title", "old_value": null, "new_value": "Hello"}],
      "changed_at": "2026-08-24T10:00:00Z"
    }]
  }' | jq '.results[0].status'
# → "applied"

# Concurrent write from device-B (same field, forked from initial state)
curl -s -X POST https://your-worker.workers.dev/sync \
  -H "Content-Type: application/json" \
  -d '{
    "changes": [{
      "record_id": "note-1",
      "table_name": "notes",
      "device_id": "device-B",
      "client_clock": {"device-B": 1},
      "changes": [{"field": "title", "old_value": null, "new_value": "World"}],
      "changed_at": "2026-08-24T10:00:01Z"
    }]
  }' | jq '{status: .results[0].status, conflicts: .results[0].conflicts}'
# → status: "conflict", conflicts: [{field: "title", resolution: "server_wins", ...}]

# Incremental pull — fetch records changed in the last hour
curl -s "https://your-worker.workers.dev/sync/notes?since=$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" | jq .count
```

## Related

- `workers-durable-objects-sync.md` — per-record Durable Object for high-contention sync scenarios
- `workers-d1-transactions.md` — D1 batch operations for atomic multi-record sync

## Sources

- [Time, Clocks, and the Ordering of Events — Lamport (1978)](https://lamport.azurewebsites.net/pubs/time-clocks.pdf)
- [CRDTs for mobile offline sync — crdt.tech](https://crdt.tech/)
- [Three-way merge (version control)](https://en.wikipedia.org/wiki/Merge_%28version_control%29#Three-way_merge)
- [Cloudflare D1 — Worker API](https://developers.cloudflare.com/d1/worker-api/d1-database/)
- [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/)
