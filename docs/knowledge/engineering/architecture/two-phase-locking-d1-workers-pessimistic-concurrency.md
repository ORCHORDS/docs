# Two-Phase Locking (2PL) D1 Workers — Pessimistic Concurrency Control

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A seat-reservation system allows two concurrent Workers to read the same available seat, both decide it is free, and both complete the booking — resulting in a double-sell. Optimistic concurrency control (OCC) resolves this with retries, but in high-contention scenarios retries cascade into thundering herds. Two-phase locking (2PL) prevents conflicts up front by acquiring locks *before* reading protected resources.

## Context

Two-phase locking is a pessimistic concurrency protocol with two phases:

- **Growing phase** — transactions acquire all needed locks (shared `S` or exclusive `X`) and never release any.
- **Shrinking phase** — transactions release locks; no new locks may be acquired.

D1 is SQLite-backed; it supports `BEGIN IMMEDIATE` (write lock on the file), but application-level row locks require an explicit `locks` table. Workers are stateless, so lock state lives in D1 itself. Strict 2PL (S2PL) holds all locks until commit or rollback, providing serializability.

---

## Lock Table Schema

```sql
CREATE TABLE IF NOT EXISTS row_locks (
  resource_id  TEXT    NOT NULL,
  lock_type    TEXT    NOT NULL CHECK (lock_type IN ('S','X')),
  holder_txn   TEXT    NOT NULL,
  acquired_at  INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL,
  PRIMARY KEY (resource_id, holder_txn)
);
CREATE INDEX IF NOT EXISTS idx_locks_resource ON row_locks(resource_id);
```

Locks have TTLs so a crashed Worker does not hold locks forever.

---

## Acquiring Locks (Growing Phase)

```typescript
const LOCK_TTL_MS = 5_000;

async function acquireLock(
  db: D1Database,
  txnId: string,
  resourceId: string,
  mode: 'S' | 'X',
): Promise<boolean> {
  const now = Date.now();
  const expires = now + LOCK_TTL_MS;

  // Expire stale locks first
  await db.prepare(
    `DELETE FROM row_locks WHERE expires_at < ?`
  ).bind(now).run();

  if (mode === 'X') {
    // Exclusive lock: no other holder allowed
    const conflict = await db
      .prepare(`SELECT 1 FROM row_locks WHERE resource_id = ? AND holder_txn != ? LIMIT 1`)
      .bind(resourceId, txnId)
      .first();
    if (conflict) return false;
  } else {
    // Shared lock: only blocked by existing X lock from another holder
    const conflict = await db
      .prepare(`SELECT 1 FROM row_locks WHERE resource_id = ? AND lock_type = 'X' AND holder_txn != ? LIMIT 1`)
      .bind(resourceId, txnId)
      .first();
    if (conflict) return false;
  }

  await db.prepare(
    `INSERT OR REPLACE INTO row_locks(resource_id, lock_type, holder_txn, acquired_at, expires_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(resourceId, mode, txnId, now, expires).run();

  return true;
}
```

---

## Executing the Critical Section

```typescript
import { nanoid } from 'nanoid';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { seatId } = await request.json<{ seatId: string }>();
    const txnId = nanoid();

    const locked = await acquireLock(env.DB, txnId, `seat:${seatId}`, 'X');
    if (!locked) {
      return Response.json({ error: 'seat_contended' }, { status: 409 });
    }

    try {
      // Growing phase complete — now safe to read and mutate
      const seat = await env.DB
        .prepare(`SELECT status FROM seats WHERE id = ?`)
        .bind(seatId)
        .first<{ status: string }>();

      if (!seat || seat.status !== 'available') {
        return Response.json({ error: 'seat_unavailable' }, { status: 409 });
      }

      await env.DB
        .prepare(`UPDATE seats SET status = 'booked' WHERE id = ?`)
        .bind(seatId)
        .run();

      return Response.json({ booked: seatId });
    } finally {
      // Shrinking phase — release lock unconditionally
      await releaseLocks(env.DB, txnId);
    }
  },
};
```

---

## Releasing Locks (Shrinking Phase)

```typescript
async function releaseLocks(db: D1Database, txnId: string): Promise<void> {
  await db
    .prepare(`DELETE FROM row_locks WHERE holder_txn = ?`)
    .bind(txnId)
    .run();
}
```

Once any lock is released, the transaction must not acquire new ones. In practice, batch all `acquireLock` calls at the start of the handler before any mutations.

---

## Deadlock Detection

2PL is susceptible to deadlocks (txn A holds `seat:1`, waits for `seat:2`; txn B holds `seat:2`, waits for `seat:1`). Mitigations:

```typescript
// Lock ordering — always acquire resource locks in sorted order
const resourceIds = ['seat:1', 'seat:2'].sort();
for (const rid of resourceIds) {
  const ok = await acquireLock(db, txnId, rid, 'X');
  if (!ok) { await releaseLocks(db, txnId); return null; }
}

// Timeout detection — any lock held past TTL is auto-expired by next acquire
// No deadlock can survive beyond LOCK_TTL_MS
```

A wait-for graph is impractical in stateless Workers; rely on TTL expiry + sorted lock ordering as the primary deadlock prevention strategy.

---

## Anti-patterns

- **Holding locks across `await fetch()`** — external I/O during the growing phase extends lock duration, causing cascading contention. Perform all external calls before acquiring locks or after releasing them.
- **Not expiring stale locks** — a Worker that throws without reaching `finally` leaves orphaned locks. Always set `expires_at` and purge on every `acquireLock` call.
- **Using 2PL for read-heavy workloads** — shared locks still block exclusive writers. Prefer MVCC / OCC for high-read, low-write tables.
- **Acquiring locks one-by-one in arbitrary order** — creates cycles. Use a canonical sort on resource IDs.

---

## Gotchas

- D1 `BEGIN IMMEDIATE` serialises *file-level* writes, not row-level. Application locks via the `row_locks` table are still required for row-level mutual exclusion across concurrent reads.
- Clock skew between Workers is irrelevant here because `Date.now()` is used only within a single Worker invocation for the TTL. However, if multiple Workers race to expire-and-insert, the delete + insert is not atomic — add a short jitter (`LOCK_TTL_MS ± 500 ms`) to reduce ABA scenarios.
- D1 has a 30-second transaction limit. Keep lock TTLs well below this.

---

## Verification

```bash
# Simulate concurrent bookings with wrk or hey
hey -n 500 -c 50 -m POST -H 'Content-Type: application/json' \
  -d '{"seatId":"A1"}' https://your-worker.workers.dev/book

# Confirm exactly one booking per seat
wrangler d1 execute YOUR_DB --command \
  "SELECT status, COUNT(*) FROM seats WHERE id='A1' GROUP BY status;"
# Expected: booked | 1
```

---

## Related

- `optimistic-concurrency-control-d1.md` — prefer when contention is low
- `lease-based-distributed-lock-d1-cas.md` — single-resource CAS-based locking
- `distributed-semaphore-durable-objects.md` — counting semaphore in DO
- `two-phase-commit-workers-d1-r2-coordination.md` — distributed commit protocol (different)
- `unit-of-work-d1-workers.md` — batching mutations

---

## Sources

- Gray & Reuter, *Transaction Processing: Concepts and Techniques*, Chapter 7 (Two-Phase Locking)
- SQLite isolation levels: https://www.sqlite.org/isolation.html
- Cloudflare D1 transactions: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
