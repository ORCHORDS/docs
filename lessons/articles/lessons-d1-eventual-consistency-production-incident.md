# D1 Eventual Consistency Production Incident: Duplicate Orders from Stale Read Replicas

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Order creation endpoint began generating duplicate orders at approximately 0.3% of request volume during a flash sale event. Investigation revealed that idempotency checks — which query the database before inserting — were returning "no existing order" even milliseconds after a successful insert. The duplicates appeared in pairs, always originating from different Cloudflare PoPs.

---

## Context

Cloudflare D1 is a distributed SQLite database built on top of Durable Objects. Writes always go to the primary (a single Durable Object), but reads can be served by read replicas in nearby PoPs to reduce latency. The replication lag between primary and replicas is typically under 100ms but can reach 200–300ms during write bursts. Our order service ran idempotency checks (`SELECT … WHERE idempotency_key = ?`) and writes (`INSERT INTO orders …`) as separate statements — without ensuring both hit the same replica or the primary. Under load, the `SELECT` executed on a replica that had not yet received the write confirmation from the primary, making the idempotency check return an empty result set and allowing a second insert to proceed.

---

## Root Cause: Read-After-Write to Different D1 Replica

D1's default behaviour routes each query independently. When two Workers instances in different PoPs receive nearly-simultaneous requests with the same idempotency key, the sequence is:

```
Worker A (PoP: DFW)                 Worker B (PoP: LAX)
  SELECT → replica-DFW (empty)        SELECT → replica-LAX (empty)
  INSERT → primary ✓                  INSERT → primary ✓  ← DUPLICATE
  replica-DFW ← replication lag …     replica-LAX ← replication lag …
```

The `INSERT` on Worker B succeeds because the primary does not yet know about Worker A's insert — they race to the primary within the same replication window.

The secondary problem was the absence of a `version` or `updated_at` column used for optimistic locking. Even if we had routed both reads to the primary, two concurrent transactions without row-level locking could still race.

```typescript
// BEFORE — broken: read and write can hit different replicas
export async function createOrder(
  db: D1Database,
  idempotencyKey: string,
  payload: OrderPayload
): Promise<Order> {
  // This SELECT may hit a read replica that is 200ms behind
  const existing = await db
    .prepare('SELECT id FROM orders WHERE idempotency_key = ?')
    .bind(idempotencyKey)
    .first<{ id: string }>();

  if (existing) return getOrder(db, existing.id);

  // INSERT goes to the primary, but the SELECT above may not have
  const result = await db
    .prepare(
      'INSERT INTO orders (id, idempotency_key, payload, version) VALUES (?, ?, ?, 1)'
    )
    .bind(crypto.randomUUID(), idempotencyKey, JSON.stringify(payload))
    .run();

  return getOrder(db, result.meta.last_row_id as unknown as string);
}
```

---

## Fix: `db.withSession()` + Optimistic Locking with a Version Column

D1 exposes `db.withSession(token)` (available since D1 session consistency GA) to pin a logical session to a bookmark. Any query within the session is guaranteed to see all writes that occurred before the session bookmark, routing to the primary when necessary.

Combine this with a `UNIQUE` constraint on `idempotency_key` at the schema level and a `version` column for optimistic locking:

```typescript
// schema migration — run once
export const MIGRATION_001 = `
  ALTER TABLE orders ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
  CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_idempotency
    ON orders (idempotency_key);
`;

// AFTER — correct: session consistency + unique constraint
export async function createOrder(
  db: D1Database,
  idempotencyKey: string,
  payload: OrderPayload
): Promise<{ order: Order; created: boolean }> {
  // Acquire a first-primary-then-replica session so subsequent reads
  // are guaranteed to see the write we are about to make.
  const session = db.withSession('first-primary');

  // Use INSERT OR IGNORE + a follow-up SELECT to handle the race atomically.
  // The UNIQUE index on idempotency_key makes the INSERT a no-op on collision.
  await session
    .prepare(
      `INSERT OR IGNORE INTO orders
         (id, idempotency_key, payload, version, created_at)
       VALUES (?, ?, ?, 1, datetime('now'))`
    )
    .bind(crypto.randomUUID(), idempotencyKey, JSON.stringify(payload))
    .run();

  // Within the same session the SELECT is guaranteed to see the row.
  const row = await session
    .prepare('SELECT *, rowid FROM orders WHERE idempotency_key = ?')
    .bind(idempotencyKey)
    .first<Order & { rowid: number }>();

  if (!row) throw new Error('Unexpected: order row missing after upsert');

  const created = row.created_at === row.updated_at; // approximation
  return { order: row, created };
}

// Optimistic locking helper for subsequent updates
export async function updateOrderStatus(
  db: D1Database,
  orderId: string,
  expectedVersion: number,
  newStatus: string
): Promise<void> {
  const session = db.withSession('first-primary');

  const result = await session
    .prepare(
      `UPDATE orders
          SET status = ?, version = version + 1, updated_at = datetime('now')
        WHERE id = ? AND version = ?`
    )
    .bind(newStatus, orderId, expectedVersion)
    .run();

  if (result.meta.changes === 0) {
    throw new ConflictError(
      `Optimistic lock failed for order ${orderId} at version ${expectedVersion}`
    );
  }
}

class ConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConflictError';
  }
}
```

---

## Monitoring / Detection

Alert when duplicate `idempotency_key` inserts are attempted — the `INSERT OR IGNORE` path emits `meta.changes === 0`, which is a detectable signal:

```typescript
import type { Env } from './types';

export async function createOrderWithMetrics(
  db: D1Database,
  env: Env,
  idempotencyKey: string,
  payload: OrderPayload
): Promise<{ order: Order; created: boolean }> {
  const session = db.withSession('first-primary');

  const insertResult = await session
    .prepare(
      `INSERT OR IGNORE INTO orders
         (id, idempotency_key, payload, version, created_at)
       VALUES (?, ?, ?, 1, datetime('now'))`
    )
    .bind(crypto.randomUUID(), idempotencyKey, JSON.stringify(payload))
    .run();

  const isDuplicate = insertResult.meta.changes === 0;

  // Emit metric so you can alert on idempotency collision rate
  env.ANALYTICS.writeDataPoint({
    blobs: ['order_create'],
    doubles: [isDuplicate ? 1 : 0],
    indexes: ['idempotency_collision'],
  });

  if (isDuplicate) {
    console.warn(`[idempotency] collision detected for key=${idempotencyKey}`);
  }

  const row = await session
    .prepare('SELECT * FROM orders WHERE idempotency_key = ?')
    .bind(idempotencyKey)
    .first<Order>();

  return { order: row!, created: !isDuplicate };
}

// Verify replication lag periodically (add to a Cron Trigger)
export async function checkReplicationLag(
  db: D1Database,
  env: Env
): Promise<void> {
  const probe = `probe-${Date.now()}`;
  const session = db.withSession('first-primary');

  const start = Date.now();
  await session
    .prepare('INSERT OR REPLACE INTO _lag_probe (key, ts) VALUES (?, ?)')
    .bind(probe, start)
    .run();

  // Immediately read back via default (potentially replica) session
  const readBack = await db
    .prepare('SELECT ts FROM _lag_probe WHERE key = ?')
    .bind(probe)
    .first<{ ts: number }>();

  const lagMs = readBack ? Date.now() - readBack.ts : -1;
  console.log(`[d1-lag] replication lag probe: ${lagMs}ms`);

  env.ANALYTICS.writeDataPoint({
    blobs: ['d1_replication_lag'],
    doubles: [lagMs],
    indexes: ['database'],
  });
}
```

---

## Anti-patterns

- **Read-then-write without session pinning** — Never rely on a `SELECT` to enforce uniqueness across distributed replicas; always use a `UNIQUE` database constraint as the authoritative guard.
- **Skipping `db.withSession()` for user-facing read-after-write** — After a write, immediately reading with a default session can return stale data. Bind writes and their confirmation reads to the same session.
- **Storing idempotency state only in KV** — KV has its own eventual consistency; do not use it as the primary idempotency store for financial transactions.
- **No version column on mutable rows** — Without optimistic locking, concurrent updates to the same order can silently clobber each other.

---

## Gotchas

- `db.withSession('first-primary')` routes the first query to the primary and subsequent queries to the nearest replica that has caught up to that bookmark. The first query will have higher latency than a normal replica read.
- `INSERT OR IGNORE` silently swallows constraint violations; always follow it with a `SELECT` within the same session to retrieve the authoritative row.
- D1 session tokens are opaque strings; do not store them in KV or pass them to clients — they are server-side booking metadata only.
- The `version` column requires all update paths (background jobs, admin tooling) to honour the optimistic lock; a single unguarded `UPDATE` defeats the mechanism.
- During D1 outages the `withSession('first-primary')` path will fail before the replica path does — design fallback UX accordingly.

---

## Verification

```bash
# Apply schema migration
npx wrangler d1 execute <DB_NAME> --remote --command "
  ALTER TABLE orders ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
  CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_idempotency ON orders (idempotency_key);
"

# Smoke-test idempotency: sending the same key twice should create one row
curl -s -X POST https://your-worker.example.com/orders \
  -H 'Idempotency-Key: test-idem-001' \
  -H 'Content-Type: application/json' \
  -d '{"item":"guitar-pick","qty":1}' | jq .id

curl -s -X POST https://your-worker.example.com/orders \
  -H 'Idempotency-Key: test-idem-001' \
  -H 'Content-Type: application/json' \
  -d '{"item":"guitar-pick","qty":1}' | jq .id

# Both commands should print the same UUID

# Check for collision metrics in Analytics Engine
npx wrangler analytics-engine query \
  --dataset idempotency_collision \
  --query "SELECT SUM(double1) as collisions FROM DATASET WHERE blob1='order_create'"
```

---

## Related

- `lessons-kv-cache-stampede-production.md`
- `lessons-durable-objects-websocket-hibernation-lost-state.md`

---

## Sources

- Cloudflare D1 Session Consistency — https://developers.cloudflare.com/d1/reference/consistency/
- Cloudflare D1 `withSession` API — https://developers.cloudflare.com/d1/worker-api/d1-database/#withsession
- SQLite `INSERT OR IGNORE` — https://www.sqlite.org/lang_conflict.html
