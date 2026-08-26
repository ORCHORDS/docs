# D1 Vector Clock Distributed Conflict Resolution

- Date: 2026-08-22
- Author: example.com
- Status: production

## Multi-writer conflict resolution for D1 databases

Cloudflare D1 is a single-writer SQLite database replicated globally for reads.
When mobile clients or edge Workers write independently and later sync, last-write-wins
by wall-clock time silently drops concurrent updates. Vector clocks give each writer a
logical timestamp that captures causal ordering, so conflicts are detected and resolved
explicitly rather than silently.

## Context

D1 exposes a single primary writer. Offline mobile clients and multiple Worker instances
that buffer writes locally before syncing create a classic multi-writer scenario. Vector
clocks track "which node had seen which version when it produced this write", enabling
three outcomes: fast-forward (one side strictly dominates), conflict (concurrent edits),
or no-op (duplicate delivery).

## Vector Clock Schema in D1

```sql
-- One row per logical entity being replicated.
CREATE TABLE IF NOT EXISTS documents (
  id          TEXT PRIMARY KEY,
  content     TEXT NOT NULL,
  -- JSON object {"nodeA":3,"nodeB":1,...}
  vector_clock TEXT NOT NULL DEFAULT '{}',
  updated_at  INTEGER NOT NULL  -- Unix ms, for tie-breaking / TTL
);

-- Pending outbox written by mobile clients before sync.
CREATE TABLE IF NOT EXISTS outbox (
  op_id        TEXT PRIMARY KEY,   -- client-generated UUIDv4
  entity_id    TEXT NOT NULL,
  payload      TEXT NOT NULL,      -- full new content
  clock        TEXT NOT NULL,      -- vector clock at write time
  node_id      TEXT NOT NULL,
  created_at   INTEGER NOT NULL
);
```

Node IDs can be Worker names (`worker-eu`) or mobile device IDs (`mobile-abc123`).
Keep clocks small: only include nodes that have actually written the entity.

## Workers Middleware: Applying Vector Clocks

```typescript
// src/middleware/vector-clock.ts
export type VectorClock = Record<string, number>;

export function increment(clock: VectorClock, nodeId: string): VectorClock {
  return { ...clock, [nodeId]: (clock[nodeId] ?? 0) + 1 };
}

/** -1 = a dominated by b, 0 = concurrent, 1 = a dominates b */
export function compare(a: VectorClock, b: VectorClock): -1 | 0 | 1 {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  let aAhead = false;
  let bAhead = false;
  for (const k of keys) {
    const av = a[k] ?? 0;
    const bv = b[k] ?? 0;
    if (av > bv) aAhead = true;
    if (bv > av) bAhead = true;
  }
  if (aAhead && !bAhead) return 1;
  if (bAhead && !aAhead) return -1;
  return 0; // concurrent
}

export function merge(a: VectorClock, b: VectorClock): VectorClock {
  const result: VectorClock = { ...a };
  for (const [k, v] of Object.entries(b)) {
    result[k] = Math.max(result[k] ?? 0, v);
  }
  return result;
}
```

```typescript
// src/handlers/sync.ts
import { compare, increment, merge, VectorClock } from '../middleware/vector-clock';

interface SyncPayload {
  op_id: string;
  entity_id: string;
  payload: string;
  clock: VectorClock;
  node_id: string;
}

export async function handleSync(
  db: D1Database,
  ops: SyncPayload[],
  serverNodeId: string,
): Promise<{ applied: string[]; conflicts: string[] }> {
  const applied: string[] = [];
  const conflicts: string[] = [];

  for (const op of ops) {
    const row = await db
      .prepare('SELECT content, vector_clock FROM documents WHERE id = ?')
      .bind(op.entity_id)
      .first<{ content: string; vector_clock: string }>();

    if (!row) {
      // New entity — insert directly.
      const newClock = increment(op.clock, serverNodeId);
      await db
        .prepare(
          'INSERT INTO documents (id, content, vector_clock, updated_at) VALUES (?, ?, ?, ?)',
        )
        .bind(op.entity_id, op.payload, JSON.stringify(newClock), Date.now())
        .run();
      applied.push(op.op_id);
      continue;
    }

    const serverClock: VectorClock = JSON.parse(row.vector_clock);
    const cmp = compare(op.clock, serverClock);

    if (cmp === 1) {
      // Client strictly ahead — fast-forward server.
      const newClock = increment(merge(op.clock, serverClock), serverNodeId);
      await db
        .prepare(
          'UPDATE documents SET content = ?, vector_clock = ?, updated_at = ? WHERE id = ?',
        )
        .bind(op.payload, JSON.stringify(newClock), Date.now(), op.entity_id)
        .run();
      applied.push(op.op_id);
    } else if (cmp === -1) {
      // Server is ahead — client's write is stale; discard.
      applied.push(op.op_id); // ack so client stops retrying
    } else {
      // Concurrent — conflict; escalate to merge strategy.
      const resolved = await resolveConflict(row.content, op.payload, serverClock, op.clock);
      const mergedClock = increment(merge(serverClock, op.clock), serverNodeId);
      await db
        .prepare(
          'UPDATE documents SET content = ?, vector_clock = ?, updated_at = ? WHERE id = ?',
        )
        .bind(resolved, JSON.stringify(mergedClock), Date.now(), op.entity_id)
        .run();
      conflicts.push(op.op_id);
    }
  }

  return { applied, conflicts };
}

async function resolveConflict(
  serverContent: string,
  clientContent: string,
  _serverClock: VectorClock,
  _clientClock: VectorClock,
): Promise<string> {
  // Domain-specific merge: for plain text use server wins; for JSON objects
  // deep-merge, preferring the client's fields on conflict.
  try {
    const s = JSON.parse(serverContent);
    const c = JSON.parse(clientContent);
    return JSON.stringify({ ...s, ...c });
  } catch {
    // Non-JSON: last-write-wins by wall clock (client just wrote).
    return clientContent;
  }
}
```

## Sync Protocol for Mobile Offline Clients

Mobile clients maintain a local SQLite (via sqlite-wasm or native) with the same outbox
schema. On reconnect:

```typescript
// Mobile pseudocode (React Native / Expo SQLite)
async function syncOutbox(serverUrl: string, localDb: SQLiteDatabase) {
  const pending = await localDb.getAllAsync<SyncPayload>(
    'SELECT op_id, entity_id, payload, clock, node_id FROM outbox ORDER BY created_at',
  );
  if (pending.length === 0) return;

  const res = await fetch(`${serverUrl}/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ops: pending }),
  });
  const { applied, conflicts } = await res.json();

  // Remove acknowledged operations from outbox.
  const ids = [...applied, ...conflicts].map((id) => `'${id}'`).join(',');
  await localDb.runAsync(`DELETE FROM outbox WHERE op_id IN (${ids})`);

  // Pull server state for conflict entities so client converges.
  if (conflicts.length > 0) {
    await pullConflictedEntities(serverUrl, localDb, conflicts);
  }
}
```

The Worker endpoint is a plain `fetch` handler that calls `handleSync` and returns JSON.
Use D1 batch API to apply multiple ops in a single round-trip when the batch is conflict-free.

## Anti-patterns

- Comparing vector clocks with `>` on wall-clock `updated_at` — concurrent writes from
  two nodes with synced clocks will flip-flop silently.
- Storing vector clocks outside the entity row (separate table) — adds a JOIN and a
  TOCTOU race window on update.
- Growing clocks unboundedly — prune nodes with a 0 component or nodes unseen for
  > 30 days during a periodic compaction job.
- Using UUIDs for node IDs in the clock object — keeps clocks large; use short stable
  identifiers (8–16 chars).

## Gotchas

- D1 does not support `SELECT ... FOR UPDATE`; use optimistic concurrency by including
  the last-known vector clock in the `WHERE` clause and checking `meta.changes === 1`.
- D1 batch (`db.batch(...)`) is a single HTTP round-trip but each statement is its own
  transaction; a later statement in a batch can fail while earlier ones committed.
- Mobile clients that are offline for extended periods accumulate large outboxes;
  implement a max-batch-size (e.g. 100 ops) and paginate sync calls.
- Vector clocks require globally unique node IDs. D1 Workers run across many isolates;
  use the Worker's `CF-Ray` prefix or a pre-assigned env var, not `Math.random()`.

## Verification

```sql
-- Inspect clock divergence across recently updated documents.
SELECT id,
       vector_clock,
       updated_at,
       json_array_length(json_each.value) AS clock_entries
FROM documents, json_each(vector_clock)
WHERE updated_at > unixepoch('now', '-1 hour') * 1000
ORDER BY updated_at DESC
LIMIT 20;
```

```typescript
// Unit test: concurrent write detected.
import { compare } from '../src/middleware/vector-clock';
const a = { node1: 2, node2: 1 };
const b = { node1: 1, node2: 2 };
console.assert(compare(a, b) === 0, 'concurrent writes must return 0');
```

## Related

- `d1-crdt-offline-sync.md`
- `sqlite-wasm-offline-d1-sync.md`
- `d1-soft-delete-workers-middleware.md`
- `d1-batch-operations-performance.md`

## Sources

- Leslie Lamport, "Time, Clocks, and the Ordering of Events in a Distributed System", 1978
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Colin Faber, "Vector Clocks in Practice", 2021
