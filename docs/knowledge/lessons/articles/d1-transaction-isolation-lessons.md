# D1 Transaction Isolation and Concurrent Write Conflicts — Lessons Learned

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

During a high-traffic event our job-queue processor — backed by Cloudflare D1 — began throwing
`SQLITE_BUSY` errors at roughly 40 req/s. Duplicate rows appeared in the `events` table and
certain counters were silently under-counted. The system recovered on its own once traffic dropped,
but not before customer-visible anomalies had accumulated.

---

## Context

D1 is a globally-distributed SQLite database. At write time, every mutation is serialised through
a single leader. This means:

- **No true parallel writes.** Concurrent `INSERT`/`UPDATE`/`DELETE` requests queue behind one
  another at the storage layer.
- **Optimistic locking has sharp edges.** If you implement your own version-column check-and-swap
  you must handle the case where two workers read the same version simultaneously and both try to
  commit.
- **Transactions do not span network calls.** A D1 `batch()` is the closest primitive to a
  multi-statement transaction; a raw `exec()` is auto-committed.

Our architecture at the time of the incident:

```
Worker A ──┐
Worker B ──┼──► D1 leader (serialised) ──► SQLite WAL
Worker C ──┘
```

We were using naïve optimistic locking:

```typescript
// BAD — race window between SELECT and UPDATE
async function incrementCounter(db: D1Database, id: string): Promise<void> {
  const row = await db
    .prepare('SELECT version, value FROM counters WHERE id = ?')
    .bind(id)
    .first<{ version: number; value: number }>();

  if (!row) throw new Error('Counter not found');

  const result = await db
    .prepare(
      'UPDATE counters SET value = ?, version = ? WHERE id = ? AND version = ?'
    )
    .bind(row.value + 1, row.version + 1, id, row.version)
    .run();

  // result.meta.changes === 0 means another worker won the race
  // but we were not retrying — we just silently dropped the write
  if (result.meta.changes === 0) {
    console.warn('CAS miss — increment lost');
  }
}
```

---

## Solution

### 1. Use `batch()` for atomic multi-statement work

`D1Database.batch()` sends a list of prepared statements to D1 and executes them in a single
round-trip inside an implicit transaction. If any statement fails the whole batch is rolled back.

```typescript
import type { D1Database } from '@cloudflare/workers-types';

export async function atomicTransfer(
  db: D1Database,
  fromId: string,
  toId: string,
  amount: number
): Promise<void> {
  const debit = db
    .prepare('UPDATE accounts SET balance = balance - ? WHERE id = ? AND balance >= ?')
    .bind(amount, fromId, amount);

  const credit = db
    .prepare('UPDATE accounts SET balance = balance + ? WHERE id = ?')
    .bind(amount, toId);

  const [debitResult, creditResult] = await db.batch([debit, credit]);

  if (debitResult.meta.changes === 0) {
    throw new Error(`Insufficient funds or account not found: ${fromId}`);
  }
}
```

### 2. Retry CAS with exponential back-off and jitter

When you must use optimistic locking, always retry on CAS miss:

```typescript
const MAX_RETRIES = 5;
const BASE_DELAY_MS = 20;

async function incrementCounterSafe(
  db: D1Database,
  id: string
): Promise<number> {
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    const row = await db
      .prepare('SELECT version, value FROM counters WHERE id = ?')
      .bind(id)
      .first<{ version: number; value: number }>();

    if (!row) throw new Error(`Counter not found: ${id}`);

    const next = row.value + 1;
    const result = await db
      .prepare(
        'UPDATE counters SET value = ?, version = ? WHERE id = ? AND version = ?'
      )
      .bind(next, row.version + 1, id, row.version)
      .run();

    if (result.meta.changes > 0) return next; // success

    // Exponential back-off with full jitter
    const delay = BASE_DELAY_MS * 2 ** attempt * Math.random();
    await new Promise((r) => setTimeout(r, delay));
  }

  throw new Error(`CAS failed after ${MAX_RETRIES} retries for counter: ${id}`);
}
```

### 3. Prefer server-side mutations over read-modify-write

For counters, push the arithmetic into SQL so the read and write are one statement:

```typescript
export async function incrementCounterAtomic(
  db: D1Database,
  id: string,
  delta = 1
): Promise<void> {
  const result = await db
    .prepare('UPDATE counters SET value = value + ? WHERE id = ?')
    .bind(delta, id)
    .run();

  if (result.meta.changes === 0) {
    throw new Error(`Counter not found: ${id}`);
  }
}
```

SQLite serialises writes, so `value + ?` is safe — no external read-modify-write race.

---

## Implementation Details

### Batch size limits

D1 batches are limited to **100 statements** per call. For bulk imports, chunk your statements:

```typescript
async function bulkInsert(
  db: D1Database,
  rows: Array<{ id: string; payload: string }>
): Promise<void> {
  const CHUNK = 100;

  for (let i = 0; i < rows.length; i += CHUNK) {
    const stmts = rows.slice(i, i + CHUNK).map((r) =>
      db
        .prepare('INSERT OR IGNORE INTO events (id, payload) VALUES (?, ?)')
        .bind(r.id, r.payload)
    );
    await db.batch(stmts);
  }
}
```

### Detecting contention in production

Log `result.meta.duration` and the number of CAS retries:

```typescript
interface CounterResult {
  value: number;
  retries: number;
  durationMs: number;
}

async function incrementWithMetrics(
  db: D1Database,
  id: string
): Promise<CounterResult> {
  const start = Date.now();
  let retries = 0;

  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    retries = attempt;
    const row = await db
      .prepare('SELECT version, value FROM counters WHERE id = ?')
      .bind(id)
      .first<{ version: number; value: number }>();
    if (!row) throw new Error('not found');

    const result = await db
      .prepare(
        'UPDATE counters SET value = value + 1, version = version + 1 WHERE id = ? AND version = ?'
      )
      .bind(id, row.version)
      .run();

    if (result.meta.changes > 0) {
      return {
        value: row.value + 1,
        retries,
        durationMs: Date.now() - start,
      };
    }

    await new Promise((r) =>
      setTimeout(r, BASE_DELAY_MS * 2 ** attempt * Math.random())
    );
  }

  throw new Error('Max retries exceeded');
}
```

---

## Anti-patterns

| Anti-pattern | Why it hurts |
|---|---|
| Silent CAS-miss drop | Data loss with no observable error |
| Unbounded retry loop | Turns contention into a CPU/D1-unit storm |
| Holding a D1 connection open across `await fetch()` | D1 has no long-lived connection; each call is HTTP — this just wastes time |
| Reading before writing when SQL can do it atomically | Unnecessary round-trip plus a race window |
| Using `exec()` for multi-statement work | Each statement auto-commits; no rollback on partial failure |

---

## Gotchas

1. **`batch()` is NOT a BEGIN/COMMIT transaction** in the SQLite sense. It runs statements
   sequentially in one implicit transaction, but there is no savepoint support.

2. **Row-level locking does not exist in SQLite** — the entire database is locked during a write.
   Under sustained contention even a single slow batch will queue every other writer.

3. **D1's read replicas serve `SELECT` statements** from the nearest location. If you do a write
   followed immediately by a read in the same request you may read stale data from a replica that
   has not yet replicated. Use `db.prepare(...).run()` (which goes to the leader) rather than
   `.first()` or `.all()` when you need read-your-own-writes consistency right after a mutation.

4. **`SQLITE_BUSY` on D1 is surfaced as a 500 with message `database is locked`** — make sure your
   error handler catches this string and retries rather than surfaces it to the user.

5. **CPU time counts during D1 waits.** D1 calls do not pause the Workers CPU clock. A long retry
   loop can exhaust the 30 s CPU-time limit before the wall clock hits 30 s.

---

## Verification

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { env } from 'cloudflare:test';

describe('D1 concurrent write safety', () => {
  beforeEach(async () => {
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS counters (
        id TEXT PRIMARY KEY,
        value INTEGER NOT NULL DEFAULT 0,
        version INTEGER NOT NULL DEFAULT 0
      )
    `);
    await env.DB.prepare(
      "INSERT OR REPLACE INTO counters (id, value, version) VALUES ('test', 0, 0)"
    ).run();
  });

  it('atomic SQL increment never loses a write', async () => {
    const ops = Array.from({ length: 20 }, () =>
      incrementCounterAtomic(env.DB, 'test')
    );
    await Promise.all(ops);
    const row = await env.DB.prepare(
      "SELECT value FROM counters WHERE id = 'test'"
    ).first<{ value: number }>();
    expect(row?.value).toBe(20);
  });
});
```

---

## Related

- `documentation/docs/policies/lessons/workers-queue-consumer-backpressure-lessons.md`
- `documentation/docs/policies/architecture/d1-schema-design.md`
- Cloudflare D1 documentation — Transactions

---

## Sources

- Cloudflare D1 beta changelog (2024–2026)
- Internal postmortem: `incidents/2025-11-job-queue-duplicate-rows.md`
- SQLite WAL mode documentation
- "Optimistic vs. Pessimistic Locking", Martin Fowler's PoEAA
