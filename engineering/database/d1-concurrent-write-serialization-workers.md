# D1 Concurrent Write Serialization Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Multiple Worker instances write to the same D1 row at the same time — updating a
counter, claiming a job from a queue, decrementing inventory, or toggling a status
flag.  Without coordination, two Workers read the same value, both compute an
increment, and one update silently overwrites the other, producing a lost-write race.
You need a way to serialise these writes without running a Durable Object or an
external lock service.

---

## Context

D1 runs on SQLite, and SQLite's WAL mode allows concurrent readers but serialises
writers: at any instant only one write transaction can hold the database-level write
lock.  This means D1 already serialises writes at the storage layer — two simultaneous
`UPDATE` statements will not corrupt each other.  The problem is at the
**application layer**: a read-modify-write sequence that spans two D1 calls (read the
balance, then update it) is not atomic.  Between the read and the write, another
Worker can interleave its own read-modify-write cycle.

The solutions in ascending order of complexity:

1. **Atomic SQL expressions** — push the computation into the SQL statement so the
   read and write are one atomic operation.
2. **Optimistic locking** — read a version column, compute the new value, write only
   if the version has not changed; retry on conflict.
3. **SELECT … FOR UPDATE equivalent via `BEGIN EXCLUSIVE`** — SQLite does not support
   row-level locks, but `BEGIN EXCLUSIVE` prevents any other writer from opening a
   transaction until the current one commits, giving serialised access.

---

## Pattern 1 — Atomic SQL expression (preferred when possible)

Push arithmetic or state transitions entirely into the SQL UPDATE.  No application-level
read is needed, so there is no window for a race.

```typescript
// src/lib/inventory.ts
import type { D1Database } from '@cloudflare/workers-types';

/**
 * Atomically decrement inventory by `qty`.
 * Returns the new quantity, or null if the item does not exist or
 * would go negative (enforced by CHECK constraint).
 */
export async function reserveInventory(
  db: D1Database,
  itemId: string,
  qty: number,
): Promise<number | null> {
  const result = await db
    .prepare(
      `UPDATE inventory
       SET quantity = quantity - ?1,
           updated_at = unixepoch()
       WHERE item_id = ?2
         AND quantity >= ?1
       RETURNING quantity`,
    )
    .bind(qty, itemId)
    .first<{ quantity: number }>();

  return result?.quantity ?? null;  // null = insufficient stock or not found
}

/**
 * Atomically increment a counter (no read needed).
 */
export async function incrementCounter(
  db: D1Database,
  name: string,
  by = 1,
): Promise<number> {
  const row = await db
    .prepare(
      `INSERT INTO counters (name, value) VALUES (?1, ?2)
       ON CONFLICT (name) DO UPDATE SET value = value + ?2
       RETURNING value`,
    )
    .bind(name, by)
    .first<{ value: number }>();

  return row!.value;
}
```

Schema for the above:

```sql
CREATE TABLE IF NOT EXISTS inventory (
  item_id    TEXT    PRIMARY KEY,
  quantity   INTEGER NOT NULL CHECK (quantity >= 0),
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
) STRICT;

CREATE TABLE IF NOT EXISTS counters (
  name  TEXT    PRIMARY KEY,
  value INTEGER NOT NULL DEFAULT 0
) STRICT;
```

---

## Pattern 2 — Optimistic locking with version column

When the computation is complex enough that it cannot be expressed as a single SQL
expression, read the row with its `version`, compute in TypeScript, and write only
if the version has not changed.  Retry the whole cycle on conflict.

```typescript
// src/lib/optimistic.ts
import type { D1Database } from '@cloudflare/workers-types';

interface PricingRow {
  item_id: string;
  price_cents: number;
  version: number;
}

async function applyComplexPricingRule(
  db: D1Database,
  itemId: string,
  discountPct: number,
  maxRetries = 5,
): Promise<number> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    // Read current state.
    const row = await db
      .prepare(`SELECT item_id, price_cents, version FROM inventory_prices WHERE item_id = ?1`)
      .bind(itemId)
      .first<PricingRow>();

    if (!row) throw new Error(`Item ${itemId} not found`);

    // Compute new price (arbitrary business logic here).
    const newPrice = Math.round(row.price_cents * (1 - discountPct / 100));

    // Write only if version still matches.
    const result = await db
      .prepare(
        `UPDATE inventory_prices
         SET price_cents = ?1, version = version + 1, updated_at = unixepoch()
         WHERE item_id = ?2 AND version = ?3
         RETURNING version`,
      )
      .bind(newPrice, itemId, row.version)
      .first<{ version: number }>();

    if (result) return newPrice;   // Write succeeded.

    // Conflict: another writer incremented version; wait briefly and retry.
    const backoffMs = 20 * Math.pow(2, attempt) + Math.random() * 10;
    await new Promise(r => setTimeout(r, backoffMs));
  }

  throw new Error(`Optimistic lock conflict on ${itemId} after ${maxRetries} retries`);
}
```

---

## Pattern 3 — BEGIN EXCLUSIVE for multi-statement critical sections

When you need to read and write multiple rows atomically and cannot express the logic
as a single SQL statement, use `BEGIN EXCLUSIVE`.  This blocks all other writers for
the duration of the transaction.  Keep the critical section short to minimise
contention.

```typescript
// src/lib/exclusive-tx.ts
import type { D1Database } from '@cloudflare/workers-types';

interface JobRow {
  id: string;
  status: string;
  payload: string;
}

/**
 * Claim the next available job from the queue.
 * BEGIN EXCLUSIVE ensures no two Workers claim the same job.
 */
export async function claimNextJob(db: D1Database): Promise<JobRow | null> {
  // D1 does not expose a direct BEGIN/COMMIT API, but you can issue
  // raw SQL statements via prepare().run() in sequence within a batch.
  // Use batch() to wrap the critical section atomically at the D1 level.
  const results = await db.batch<{ changes: number } | JobRow>([
    db.prepare(`BEGIN EXCLUSIVE`),

    db.prepare(
      `UPDATE jobs
       SET status = 'claimed', claimed_at = unixepoch()
       WHERE id = (
         SELECT id FROM jobs
         WHERE status = 'pending'
         ORDER BY created_at ASC
         LIMIT 1
       )
       RETURNING id, payload, status`,
    ),

    db.prepare(`COMMIT`),
  ]);

  // results[1] is the RETURNING output from the UPDATE.
  const updateResult = results[1] as D1Result<JobRow>;
  return updateResult.results?.[0] ?? null;
}
```

> **Note**: D1 wraps each `db.batch()` call in an implicit transaction.  Explicitly
> issuing `BEGIN EXCLUSIVE` inside a batch upgrades it to an exclusive transaction for
> the duration of that batch.  Do not mix `BEGIN`/`COMMIT` with multi-statement
> batches that already use the implicit transaction — doing so can leave the
> connection in an unexpected state.

---

## Serialization throughput limits

D1 serialises all writers at the database level.  Under high concurrency, exclusive
transactions become a bottleneck.  Approximate benchmarks on a lightly loaded D1
database:

| Pattern | Safe write rate (req/s) |
|---|---|
| Atomic SQL expression (`UPDATE … SET x = x + 1`) | ~500–1 000 |
| Optimistic locking (1–2 retries typical) | ~200–400 |
| `BEGIN EXCLUSIVE` + multi-statement | ~100–200 |
| Durable Object serialised queue | ~1 000+ (single-threaded) |

If your write rate consistently exceeds 200 req/s on a single row, a Durable Object
with an in-memory queue is more scalable.

---

## Anti-patterns

- **Read-modify-write in two separate D1 calls without a version check** — this is the
  classic lost-update race.  Any pattern that reads a value, computes in TypeScript,
  and then writes it back in a second call is vulnerable.

- **Long-running exclusive transactions** — every millisecond a `BEGIN EXCLUSIVE`
  transaction is open, other Workers queue behind it.  If your critical section
  involves slow I/O (KV, R2, external fetch), do that I/O outside the transaction and
  pass the result in.

- **Ignoring the return value of `RETURNING`** — after a conditional UPDATE, always
  check whether `RETURNING` produced a row.  A missing row means the condition was
  false (version mismatch, insufficient stock, row gone) — that is the conflict signal.

- **Retrying indefinitely** — jittered exponential backoff with a maximum retry count
  prevents thundering-herd storms under load.  Always throw after the final retry so
  callers can surface the error rather than spinning forever.

---

## Gotchas

- SQLite in WAL mode serialises writers at the file level, not the row level.  There
  are no row-level locks.  `BEGIN EXCLUSIVE` is the only mechanism that prevents
  interleaving from concurrent connections.

- `db.batch()` is atomic at the D1 API layer but the semantics differ from a classical
  SQL transaction: if a statement in the batch fails, D1 rolls back all statements in
  the batch.  However, `BEGIN EXCLUSIVE` inside a batch still acquires the write lock;
  a failure still triggers an implicit ROLLBACK that releases it.

- The `RETURNING` clause requires SQLite ≥ 3.35.  D1 runs a recent SQLite build that
  supports it, but if you test locally with an older SQLite CLI you may get syntax
  errors.

- Workers can be evicted mid-request.  If a Worker is killed after `BEGIN EXCLUSIVE`
  but before `COMMIT`, SQLite times out the lock after a configurable busy-timeout and
  another Writer can proceed.  D1 sets this timeout; you do not need to configure it.

---

## Verification

```typescript
import { describe, it, expect, beforeAll } from 'vitest';
import { env } from 'cloudflare:test';
import { reserveInventory, incrementCounter } from '../src/lib/inventory';

describe('concurrent write serialization', () => {
  beforeAll(async () => {
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS inventory (
        item_id TEXT PRIMARY KEY, quantity INTEGER NOT NULL CHECK (quantity >= 0),
        updated_at INTEGER NOT NULL DEFAULT (unixepoch())
      ) STRICT;
      INSERT OR IGNORE INTO inventory VALUES ('sku-1', 10, unixepoch());

      CREATE TABLE IF NOT EXISTS counters (
        name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0
      ) STRICT;
    `);
  });

  it('atomic decrement prevents oversell', async () => {
    // Simulate 12 concurrent reservation attempts for quantity=10.
    const results = await Promise.all(
      Array.from({ length: 12 }, () => reserveInventory(env.DB, 'sku-1', 1)),
    );
    const successes = results.filter(r => r !== null).length;
    expect(successes).toBe(10);
  });

  it('counter increments without race', async () => {
    await Promise.all(Array.from({ length: 50 }, () => incrementCounter(env.DB, 'hits')));
    const row = await env.DB.prepare('SELECT value FROM counters WHERE name = ?').bind('hits').first<{ value: number }>();
    expect(row?.value).toBe(50);
  });
});
```

---

## Related

- `d1-optimistic-locking-version-column-workers.md` — deeper treatment of the version
  column pattern.
- `d1-durable-objects-serialized-writes-workers.md` — using a Durable Object as a
  single-writer queue for higher throughput serialization.
- `d1-advisory-lock-pattern-workers.md` — application-level advisory locks in D1.
- `d1-savepoint-nested-transaction-workers.md` — nested transaction control with
  SAVEPOINT.
- `d1-dead-letter-queue-retry-workers.md` — retry infrastructure for failed writes.

---

## Sources

- SQLite WAL mode and concurrency: https://www.sqlite.org/wal.html
- SQLite locking and concurrency: https://www.sqlite.org/lockingv3.html
- Cloudflare D1 batch operations: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite RETURNING clause: https://www.sqlite.org/lang_returning.html
