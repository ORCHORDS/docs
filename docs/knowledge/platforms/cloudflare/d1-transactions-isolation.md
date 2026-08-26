# d1-transactions-isolation

**Issue:** D1 transaction isolation (serializable), BEGIN/COMMIT/ROLLBACK in Workers, concurrent writes, WAL mode
**Date:** 2026-08-11
**Status:** documented

## Symptom
Two Workers read the same balance, both decrement it, and the account
goes negative. You use sequential `.run()` calls but the second fails
and the first already committed. You try `BEGIN TRANSACTION` but get
`TypeError: D1 does not support multi-statement queries`.

## Root cause
**D1 uses SQLite in WAL mode with serializable isolation.** Concurrent
writes are serialized at the database level. Transactions must use
`db.batch()` with raw SQL statements, not multi-statement strings. A
single `.run()` call is auto-committed; there is no multi-statement
API outside of `batch()`.

**Source:** https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements

## D1 isolation model

D1 runs SQLite with:
- **WAL mode** (Write-Ahead Logging): readers don't block writers;
  writers don't block readers. Multiple concurrent reads are fine.
- **Serializable isolation**: only one write transaction executes at
  a time. Concurrent write requests queue behind the active writer.
- **No MVCC snapshot isolation**: a read inside a write transaction
  sees committed data up to the point the transaction started.

This means:
- Read-read: concurrent, no locking
- Read-write: concurrent (WAL reader sees snapshot)
- Write-write: serialized — D1 queues the second writer

## Transactions via `db.batch()`

`db.batch()` executes multiple statements as a single atomic
transaction. If any statement fails, the entire batch rolls back.

```typescript
// Transfer funds atomically
async function transferFunds(
  db: D1Database,
  fromId: string,
  toId: string,
  amount: number,
): Promise<void> {
  const results = await db.batch([
    db.prepare(`UPDATE wallets SET balance = balance - ? WHERE id = ? AND balance >= ?`)
      .bind(amount, fromId, amount),
    db.prepare(`UPDATE wallets SET balance = balance + ? WHERE id = ?`)
      .bind(amount, toId),
  ]);

  // Check that the debit actually updated a row (balance check)
  const debitResult = results[0];
  if (debitResult.meta.changes === 0) {
    throw new Error("Insufficient funds or account not found");
  }
}
```

`db.batch()` returns an array of `D1Result`, one per statement, in
order. All succeed or all fail — it is atomic.

## Explicit BEGIN / COMMIT / ROLLBACK

D1 supports `BEGIN`, `COMMIT`, and `ROLLBACK` as individual `.run()`
calls. Use this when you need to read-then-write within one transaction
(SELECT + UPDATE based on the result).

```typescript
async function reserveSeat(
  db: D1Database,
  eventId: string,
  userId: string,
): Promise<boolean> {
  // BEGIN starts a write transaction
  await db.prepare("BEGIN").run();

  try {
    // Read inside the transaction — sees a consistent snapshot
    const seat = await db
      .prepare(`SELECT id FROM seats WHERE event_id = ? AND reserved = 0 LIMIT 1`)
      .bind(eventId)
      .first<{ id: string }>();

    if (!seat) {
      await db.prepare("ROLLBACK").run();
      return false; // no seats available
    }

    // Write inside the transaction
    await db
      .prepare(`UPDATE seats SET reserved = 1, user_id = ? WHERE id = ?`)
      .bind(userId, seat.id)
      .run();

    await db.prepare("COMMIT").run();
    return true;
  } catch (err) {
    // Always rollback on error to release the write lock
    await db.prepare("ROLLBACK").run().catch(() => {});
    throw err;
  }
}
```

**Important:** Between `BEGIN` and `COMMIT`, D1 holds a write lock.
Keep transactions short. Long-held locks block all other writers on
the same D1 database.

## Sequential `.run()` vs `db.batch()` vs explicit transaction

| Pattern | Atomic | Use when |
|---|---|---|
| Sequential `.run()` | No | Independent writes that can partially succeed |
| `db.batch()` | Yes | Multiple writes that must all succeed or all fail |
| `BEGIN` / `COMMIT` | Yes | Read-then-write (need to see data before deciding) |

```typescript
// ❌ Not atomic — second write can fail, first is committed
await db.prepare(`INSERT INTO orders ...`).bind(...).run();
await db.prepare(`UPDATE inventory SET qty = qty - 1 ...`).bind(...).run();

// ✅ Atomic — both or neither
await db.batch([
  db.prepare(`INSERT INTO orders ...`).bind(...),
  db.prepare(`UPDATE inventory SET qty = qty - 1 ...`).bind(...),
]);
```

## Handling concurrent writes (WAL mode behavior)

D1's WAL mode means concurrent Worker instances that write to the same
database serialize automatically — you do not need external locking.
The second writer waits for the first to commit.

However, if your Worker opens a `BEGIN` transaction and the request
times out, D1 automatically rolls back the dangling transaction after
a timeout (~5 s). Design for this:

```typescript
async function safeTransact<T>(
  db: D1Database,
  work: () => Promise<T>,
): Promise<T> {
  await db.prepare("BEGIN").run();
  try {
    const result = await work();
    await db.prepare("COMMIT").run();
    return result;
  } catch (err) {
    await db.prepare("ROLLBACK").run().catch(() => {});
    throw err;
  }
}

// Usage:
const reserved = await safeTransact(env.DB, () =>
  reserveSeatInner(env.DB, eventId, userId),
);
```

## WAL mode implications for reads

D1 enables WAL mode by default. A `SELECT` outside a transaction
always reads the latest committed state (no dirty reads). A `SELECT`
inside a `BEGIN` transaction reads the snapshot at the point `BEGIN`
was issued.

```typescript
// This SELECT sees data committed before BEGIN was issued,
// even if another Worker commits between BEGIN and the SELECT.
await db.prepare("BEGIN").run();
const snap = await db.prepare(`SELECT balance FROM wallets WHERE id = ?`)
  .bind(id)
  .first<{ balance: number }>();
// snap.balance is stable for the duration of this transaction
await db.prepare("COMMIT").run();
```

## Verification
- Run two concurrent Workers that transfer from the same wallet;
  verify the final balance is correct (no double-spend)
- Introduce an artificial error mid-batch; verify partial writes
  do not persist
- `wrangler d1 execute example project-db --command "PRAGMA journal_mode"` →
  should return `wal`
- `wrangler d1 execute example project-db --command "BEGIN; SELECT * FROM seats LIMIT 1; ROLLBACK"` →
  confirm transaction round-trips work

## Gotchas
- **The "multi-statement string" gotcha.** D1 rejects strings like
  `"BEGIN; UPDATE ...; COMMIT"` in a single `.run()` call. Use
  separate `.run()` calls or `db.batch()`.
- **The "batch is not BEGIN/COMMIT" gotcha.** `db.batch()` cannot
  include a `SELECT` that conditions subsequent writes. Use explicit
  `BEGIN`/`COMMIT` for read-then-write patterns.
- **The "long transaction" gotcha.** D1 has a ~5 s write-transaction
  timeout. If your transaction takes longer (e.g., awaiting an
  external API inside a transaction), it will be rolled back
  automatically. Do all async work outside the transaction.
- **The "D1 in Durable Objects" gotcha.** D1 accessed from inside a
  Durable Object still serializes at the D1 level, not the DO level.
  If you need strongly-ordered per-entity writes, use the DO's own
  SQL storage instead of D1.
- **The "meta.changes" check" gotcha.** An UPDATE that matches no
  rows returns `changes: 0` — not an error. Always check
  `result.meta.changes` when the update is load-bearing.

## Related
- `cloudflare/d1-best-practices.md`
- `cloudflare/d1-migration-best-practices.md`
- `cloudflare/d1-pragma-tuning.md`
- `cloudflare/durable-objects-patterns.md`
- CF D1 batch: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- CF D1 transactions: https://developers.cloudflare.com/d1/worker-api/d1-database/#transactions
- SQLite WAL mode: https://www.sqlite.org/wal.html
