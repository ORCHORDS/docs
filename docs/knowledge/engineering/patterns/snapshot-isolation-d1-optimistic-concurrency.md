# Snapshot Isolation — D1 Optimistic Concurrency

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Two Workers handle simultaneous PUT /orders/42 requests. Both read the current row, compute a discount, then write back. The second write silently overwrites the first — a classic lost-update. D1 uses SQLite under the hood; it has serialisable transactions per connection, but Workers spin up independent connections on every request. Optimistic concurrency control (OCC) using a version column recreates snapshot-level safety without distributed locks.

---

## Context

D1's SQLite engine guarantees atomicity within a single `db.batch()` or `db.prepare(...).run()` call, but concurrent Workers each see independent snapshots. OCC adds a monotonic `version` integer (or `updated_at` timestamp) to every row. A write succeeds only when the version the Worker read matches the version still in the database — otherwise it returns a 409 Conflict so the caller can retry with fresh data. No Durable Object or advisory lock is required.

---

## Schema Design

```sql
-- migration: 001_add_version.sql
CREATE TABLE orders (
  id         TEXT PRIMARY KEY,
  status     TEXT NOT NULL DEFAULT 'pending',
  total_cents INTEGER NOT NULL DEFAULT 0,
  version    INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Optional: partial index for hot in-flight rows
CREATE INDEX idx_orders_status ON orders (status) WHERE status != 'completed';
```

The `version` column is the *optimistic lock token*. Clients always receive it and must echo it back on writes.

---

## Read — Include Version in Response

```typescript
// src/handlers/get-order.ts
import type { D1Database } from '@cloudflare/workers-types';

interface Order {
  id: string;
  status: string;
  total_cents: number;
  version: number;
  updated_at: string;
}

export async function getOrder(db: D1Database, id: string): Promise<Response> {
  const order = await db
    .prepare('SELECT * FROM orders WHERE id = ?')
    .bind(id)
    .first<Order>();

  if (!order) return new Response('Not Found', { status: 404 });

  return Response.json(order);
}
```

---

## Write — Conditional UPDATE on Version

```typescript
// src/handlers/update-order.ts
import type { D1Database } from '@cloudflare/workers-types';

interface UpdatePayload {
  status: string;
  total_cents: number;
  version: number; // echoed back from the GET
}

export class ConflictError extends Error {
  constructor() { super('Version conflict'); this.name = 'ConflictError'; }
}

export async function updateOrder(
  db: D1Database,
  id: string,
  payload: UpdatePayload,
): Promise<Response> {
  const result = await db
    .prepare(`
      UPDATE orders
      SET status      = ?,
          total_cents = ?,
          version     = version + 1,
          updated_at  = datetime('now')
      WHERE id = ? AND version = ?
    `)
    .bind(payload.status, payload.total_cents, id, payload.version)
    .run();

  if (result.meta.changes === 0) {
    // Either the row does not exist, or a concurrent write bumped the version
    const exists = await db
      .prepare('SELECT 1 FROM orders WHERE id = ?')
      .bind(id)
      .first();

    if (!exists) return new Response('Not Found', { status: 404 });

    return Response.json(
      { error: 'conflict', message: 'Row was modified by another request. Fetch and retry.' },
      { status: 409 },
    );
  }

  return Response.json({ id, version: payload.version + 1 });
}
```

`result.meta.changes` is the number of rows affected. Zero means the `WHERE id = ? AND version = ?` predicate failed.

---

## Batch Read-Modify-Write (Single Round-Trip)

For workflows that read, transform, and write in a single handler, use `db.batch()` to avoid a second network hop:

```typescript
export async function applyDiscount(
  db: D1Database,
  id: string,
  discountPct: number,
  knownVersion: number,
): Promise<Response> {
  // 1. Read current row
  const order = await db
    .prepare('SELECT total_cents, version FROM orders WHERE id = ?')
    .bind(id)
    .first<{ total_cents: number; version: number }>();

  if (!order) return new Response('Not Found', { status: 404 });
  if (order.version !== knownVersion) {
    return Response.json({ error: 'conflict' }, { status: 409 });
  }

  const newTotal = Math.floor(order.total_cents * (1 - discountPct / 100));

  // 2. Conditional write
  const [writeResult] = await db.batch([
    db.prepare(`
      UPDATE orders
      SET total_cents = ?, version = version + 1
      WHERE id = ? AND version = ?
    `).bind(newTotal, id, knownVersion),
  ]);

  if (writeResult.meta.changes === 0) {
    return Response.json({ error: 'conflict' }, { status: 409 });
  }

  return Response.json({ id, total_cents: newTotal, version: knownVersion + 1 });
}
```

---

## Client-Side Retry with Backoff

```typescript
// src/client/order-client.ts
async function updateWithRetry(
  endpoint: string,
  maxAttempts = 3,
): Promise<void> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const order = await fetch(endpoint).then(r => r.json());
    const res = await fetch(endpoint, {
      method: 'PUT',
      body: JSON.stringify({ ...order, status: 'processing' }),
      headers: { 'Content-Type': 'application/json' },
    });

    if (res.ok) return;
    if (res.status === 409) {
      // Conflict: re-fetch and retry
      await sleep(50 * 2 ** attempt);
      continue;
    }
    throw new Error(`Unexpected ${res.status}`);
  }
  throw new Error('Max retry attempts reached');
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
```

---

## Anti-patterns

- **Using `updated_at` as the version token**: two writes within the same second compare equal; use a monotonic integer.
- **Checking `changes` after a `batch()`**: `db.batch()` returns an array of results; check `results[0].meta.changes`, not a top-level property.
- **Not returning the new version to the client**: after a successful write the version has incremented; clients keeping stale tokens will conflict on their next write.
- **Wrapping in a SELECT then UPDATE without a WHERE clause version check**: a separate SELECT does not provide atomicity across two statements; the `WHERE version = ?` predicate on the UPDATE is the only safe guard.
- **Using OCC for high-contention hot rows** (e.g. a global counter): if 100 Workers race to increment the same row, 99 will conflict every time. Use a Durable Object for true hot-counter workloads.

---

## Gotchas

- `result.meta.changes` can be `undefined` if the D1 binding was used in a way that returns raw results — always check for `?? 0`.
- D1 is eventually consistent across read replicas; a read from a secondary may return an older version than what was just written. For OCC the **write** must land on the primary, which it will via `db.prepare(...).run()` in the same Worker invocation.
- SQLite `INTEGER` is 64-bit; JavaScript `number` loses precision above 2^53. If `version` can ever exceed 9 007 199 254 740 991 (unlikely), return it as a string.
- In Vitest / `@cloudflare/vitest-pool-workers`, simulate conflicts by running two concurrent transactions against the same in-process D1 and asserting one returns 409.

---

## Verification

```bash
# Seed a row
npx wrangler d1 execute DB --command \
  "INSERT INTO orders (id, status, total_cents) VALUES ('ord_1', 'pending', 1000);"

# First writer grabs version=1, updates to version=2
curl -X PUT /orders/ord_1 -d '{"status":"processing","total_cents":1000,"version":1}'
# {"id":"ord_1","version":2}

# Second writer still sends version=1 — should 409
curl -X PUT /orders/ord_1 -d '{"status":"processing","total_cents":1000,"version":1}'
# {"error":"conflict","message":"Row was modified by another request. Fetch and retry."}
```

---

## Related

- `idempotency-key-pattern-workers-d1.md`
- `lease-based-concurrency-d1.md`
- `unit-of-work-pattern-d1-workers.md`
- `two-phase-commit-workers-d1-service-bindings.md`
- `distributed-lock-durable-objects.md`

---

## Sources

- SQLite documentation — "Isolation in SQLite" (2026)
- Cloudflare D1 docs — `result.meta.changes`, `db.batch()` (2026)
- Designing Data-Intensive Applications, Martin Kleppmann — ch. 7 Transactions
- Fowler, P of EAA — "Optimistic Offline Lock"
