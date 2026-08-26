# database-transaction-design

**Issue:** When to use transactions, isolation levels, D1 specifics
**Date:** 2026-08-09
**Status:** documented

## Symptom
You update two rows in a function: row A and row B. The
function succeeds for A but fails for B. The user sees an
error. But row A is updated. The data is inconsistent.

## Root cause
**By default, each statement is its own transaction.** A
multi-statement operation is not atomic. If any statement
fails, the earlier ones are already committed.

**Source:** SQLite docs (D1's engine):
https://www.sqlite.org/lang_transaction.html

> "A transaction is a sequence of operations that are
> committed or rolled back as a single unit."

## The pattern: explicit transaction

### D1 batch() (the wrong way)
D1's `batch()` is often misunderstood. It runs multiple
statements in a single HTTP request, but it's NOT a
transaction by default.

```ts
// ❌ Not a transaction (without bundler bug workaround)
await env.DB!.batch([
  env.DB!.prepare(`UPDATE accounts SET balance = balance - 100 WHERE id = 'A'`),
  env.DB!.prepare(`UPDATE accounts SET balance = balance + 100 WHERE id = 'B'`),
]);
// If A succeeds but B fails, A is still committed.
```

### D1 transaction() (the right way)
```ts
// ✅ Real transaction
const result = await env.DB!.transaction(async (txn) => {
  await txn.prepare(`UPDATE accounts SET balance = balance - 100 WHERE id = 'A'`).run();
  await txn.prepare(`UPDATE accounts SET balance = balance + 100 WHERE id = 'B'`).run();
  return { ok: true };
});
// If either fails, both are rolled back.
```

**Source:** CF D1 transactions:
https://developers.cloudflare.com/d1/platform/transactions/

> "D1 supports transactions via the `db.transaction()` method.
> Statements in a transaction are committed atomically or
> rolled back together."

### Caveat: D1's bundler bug
`db.transaction()` may have the same bundler issue as
`db.batch()`. The D1 docs and the bundler docs should be
checked; if you see the bundler stripping `sql`, you may need
to use a different pattern (see `d1-batch-bundler-bug.md`).

## Isolation levels

Different DBs offer different isolation levels. The default
varies:
- **SQLite/D1:** SERIALIZABLE (strongest)
- **Postgres:** READ COMMITTED (default)
- **MySQL:** REPEATABLE READ (default)

Higher isolation = stronger consistency but less concurrency.

For D1, the default SERIALIZABLE is fine. For Postgres, you
may need to think about isolation.

## The 4 transaction phenomena

| Phenomenon | Description |
|---|---|
| **Dirty read** | A reads uncommitted data from B |
| **Non-repeatable read** | A reads row X, B updates X, A reads X again (different value) |
| **Phantom read** | A reads a set of rows, B inserts a new row, A reads again (different set) |
| **Serialization anomaly** | Concurrent transactions produce a result that no serial execution could produce |

SQLite/D1 (SERIALIZABLE) prevents all 4. Postgres
(READ COMMITTED) prevents dirty read only.

## When to use a transaction

✅ Use a transaction when:
- **Multiple rows must change atomically** (transfer money,
  update user + their profile)
- **A read + write must be consistent** (read then update based
  on the read)
- **The business invariant depends on multiple tables**

❌ Don't use a transaction when:
- **Only one row is changing** (the statement is already
  atomic)
- **The transaction would be long-running** (locks held,
  blocking other queries)
- **You can tolerate eventual consistency** (use a queue +
  saga)

## Deadlocks

Two transactions waiting for each other:
```
Transaction A: holds row X, wants row Y
Transaction B: holds row Y, wants row X
```

Both wait forever. The DB eventually times out and kills one.

To prevent:
- **Acquire locks in a consistent order** (e.g. always lock
  row X before row Y)
- **Keep transactions short** (don't do expensive work
  inside)
- **Use a lock timeout** (let the DB kill a stuck transaction)

For D1 (SQLite), deadlocks are rare because of SERIALIZABLE
isolation + single-writer.

## Long-running transactions

A long transaction (e.g. 30 seconds) holds locks for 30
seconds. Other queries wait. The system feels slow.

Rule of thumb: a transaction should be < 1 second.

For long-running work (e.g. processing a video), use a queue
+ saga, not a transaction.

## Verification
- **Test:** `test/transactions.test.ts > transaction rolls back
  on error` — passes
- **Test:** `test/transactions.test.ts > transaction commits
  on success` — passes
- **Live:** Transaction duration is monitored; alerts on
  long transactions

## Gotchas
- **D1's `batch()` is NOT a transaction** by default. Use
  `transaction()` for atomicity.
- **A transaction inside a transaction** is fine (D1 supports
  savepoints). But keep the nesting shallow.
- **A failed transaction's error** is opaque. The error
  message may not tell you which statement failed. Log
  intermediate state for debugging.
- **The `RETURNING` clause** in INSERT/UPDATE/DELETE returns
  the affected rows. Useful for "insert + get the new ID" in
  one query.
- **Transactions have a max size** (D1: 1MB per request for
  SQLite-backed storage; 10MB for some plans). For large
  bulk operations, batch in chunks.
- **Transactions are isolated per-isolate** (CF Workers). Two
  different Workers do not share a transaction.

## Related
- `d1-batch-bundler-bug.md`
- `database-migration-strategy.md`
- `saga-pattern.md` (transactions across services)
- `patterns/repository-pattern.md`
- CF D1 transactions: https://developers.cloudflare.com/d1/platform/transactions/
