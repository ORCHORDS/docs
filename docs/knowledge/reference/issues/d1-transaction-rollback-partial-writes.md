# D1 Transaction Rollback Debugging with Partial Writes

2026-08-24 / example.com / production

---

## Symptom / Use-case

A Cloudflare D1 operation that runs multiple SQL statements appears to succeed (no exception thrown, HTTP 200 returned) yet the database ends up in a partially written state. Alternatively, an explicit `ROLLBACK` is issued but some rows written earlier in the same logical operation remain persisted. In both cases the data model is inconsistent and subsequent reads return corrupted or incomplete records.

Common patterns that trigger this:
- Using `db.batch()` with a mix of `INSERT` and `UPDATE` statements, where a later statement fails silently
- Calling `db.exec()` for multi-statement SQL that contains DDL mixed with DML (DDL auto-commits in SQLite)
- Catching an error from one statement, deciding to proceed anyway, then expecting a later `ROLLBACK` to undo the already-committed statement

---

## Context

D1 is built on SQLite, which has well-defined transaction semantics, but the D1 Workers binding introduces several layers that can obscure those semantics:

- **`db.batch()`** executes an array of prepared statements as a single HTTP request to D1. Each statement in the batch runs in its own **implicit transaction** by default — if statement 3 of 5 fails, statements 1 and 2 are already committed.
- **`db.exec()`** takes a raw SQL string and executes each statement separated by semicolons. DDL statements (`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`) cause an implicit commit in SQLite, so a rollback after them does not undo the schema change.
- **Explicit transactions** require wrapping statements with `BEGIN`/`COMMIT`/`ROLLBACK` inside a single `db.exec()` call or via a prepared statement chain using `db.prepare().run()`.
- D1's remote execution model means the transaction boundary is on the D1 server side; client-side errors (network timeouts, Worker CPU limits) may not roll back a transaction that is already in flight on the server.

---

## Diagnosing Partial Write State

### Step 1 — Confirm whether statements share a transaction

```typescript
// src/d1-transaction-test.ts
// This does NOT use a single transaction — each statement commits independently
async function batchWithoutTransaction(db: D1Database): Promise<void> {
  const results = await db.batch([
    db.prepare('INSERT INTO orders (id, status) VALUES (?, ?)').bind('ord-1', 'pending'),
    db.prepare('UPDATE inventory SET qty = qty - 1 WHERE sku = ?').bind('SKU-42'),
    db.prepare('INSERT INTO audit_log (event) VALUES (?)').bind('order.created'),
  ]);

  // If the UPDATE fails (e.g., constraint violation), the first INSERT is already committed
  console.log('batch results:', results.map(r => ({ success: r.success, error: r.error })));
}
```

### Step 2 — Use an explicit transaction via `db.exec()`

```typescript
// src/d1-explicit-transaction.ts
async function createOrderTransactional(
  db: D1Database,
  orderId: string,
  sku: string
): Promise<void> {
  // All statements in a single exec() string share the transaction context
  // when wrapped with BEGIN/COMMIT
  await db.exec(`
    BEGIN;
    INSERT INTO orders (id, status) VALUES ('${orderId}', 'pending');
    UPDATE inventory SET qty = qty - 1 WHERE sku = '${sku}';
    INSERT INTO audit_log (event) VALUES ('order.created:${orderId}');
    COMMIT;
  `);
}
```

> **Note**: The above uses string interpolation for clarity. In production, use prepared statements (see Step 3).

### Step 3 — Safe transactional pattern with prepared statements

```typescript
// src/d1-safe-transaction.ts
export async function createOrderSafe(
  db: D1Database,
  orderId: string,
  sku: string
): Promise<{ success: boolean; error?: string }> {
  try {
    // D1 does not yet support multi-statement prepared transactions in batch().
    // The workaround is a raw exec() with parameterized SQL built manually,
    // or using a single exec() with literals after server-side validation.
    const result = await db
      .prepare(
        `
        BEGIN;
        INSERT INTO orders (id, status) VALUES (?1, 'pending');
        UPDATE inventory SET qty = qty - 1 WHERE sku = ?2 AND qty > 0;
        INSERT INTO audit_log (event, ref) VALUES ('order.created', ?1);
        COMMIT;
      `
      )
      .bind(orderId, sku)
      .run();

    // Check affected rows — a successful COMMIT with 0 rows on the UPDATE
    // means the inventory constraint was not met even though no error was thrown
    if (result.meta.changes === 0) {
      // The UPDATE affected 0 rows; qty was already 0 — implicit rollback may not have occurred
      // Verify by reading back
      const inv = await db
        .prepare('SELECT qty FROM inventory WHERE sku = ?')
        .bind(sku)
        .first<{ qty: number }>();
      if (!inv || inv.qty <= 0) {
        throw new Error(`inventory exhausted for sku=${sku}`);
      }
    }

    return { success: true };
  } catch (err) {
    console.error('transaction failed, rolling back:', err);
    // Attempt explicit rollback in case the BEGIN committed but COMMIT did not
    try {
      await db.exec('ROLLBACK;');
    } catch {
      // ROLLBACK outside a transaction throws — safe to ignore
    }
    return { success: false, error: String(err) };
  }
}
```

### Step 4 — Detect partial write state post-hoc

```typescript
// src/d1-consistency-check.ts
export async function checkOrderConsistency(
  db: D1Database,
  orderId: string
): Promise<{ consistent: boolean; issues: string[] }> {
  const issues: string[] = [];

  const order = await db
    .prepare('SELECT id, status FROM orders WHERE id = ?')
    .bind(orderId)
    .first<{ id: string; status: string }>();

  const auditEntry = await db
    .prepare("SELECT 1 FROM audit_log WHERE ref = ? AND event = 'order.created'")
    .bind(orderId)
    .first();

  if (order && !auditEntry) {
    issues.push(`order ${orderId} exists but has no audit_log entry — partial write detected`);
  }

  if (!order && auditEntry) {
    issues.push(`audit_log has entry for ${orderId} but order row is missing — partial write detected`);
  }

  return { consistent: issues.length === 0, issues };
}
```

### Step 5 — Log D1 meta to surface silent failures

```typescript
// src/d1-meta-logger.ts
import type { D1Result } from '@cloudflare/workers-types';

export function assertD1Success(result: D1Result, label: string): void {
  if (!result.success) {
    throw new Error(`D1 statement failed [${label}]: ${result.error ?? 'unknown error'}`);
  }
  console.log(JSON.stringify({
    label,
    changes: result.meta.changes,
    last_row_id: result.meta.last_row_id,
    duration_ms: result.meta.duration,
  }));
}
```

### Step 6 — Reproduce in Wrangler dev for deterministic testing

```typescript
// tests/d1-transaction.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';

describe('D1 transaction rollback', () => {
  beforeEach(async () => {
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, status TEXT);
      CREATE TABLE IF NOT EXISTS inventory (sku TEXT PRIMARY KEY, qty INTEGER);
      CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT, ref TEXT);
      INSERT OR REPLACE INTO inventory VALUES ('SKU-1', 0);
    `);
  });

  it('rolls back when inventory is exhausted', async () => {
    const { createOrderSafe } = await import('../src/d1-safe-transaction');
    const result = await createOrderSafe(env.DB, 'ord-test-1', 'SKU-1');

    expect(result.success).toBe(false);

    // Confirm no partial write
    const order = await env.DB.prepare('SELECT * FROM orders WHERE id = ?')
      .bind('ord-test-1')
      .first();
    expect(order).toBeNull();

    const log = await env.DB.prepare("SELECT * FROM audit_log WHERE ref = ?")
      .bind('ord-test-1')
      .first();
    expect(log).toBeNull();
  });
});
```

---

## Anti-patterns

- **Assuming `db.batch()` is transactional** — it is not. Each statement in the array commits independently. Use explicit `BEGIN`/`COMMIT` in a single `exec()` call for true atomicity.
- **Mixing DDL and DML in a single `exec()`** — DDL causes an implicit commit; a `ROLLBACK` after a `CREATE TABLE` will not undo the schema change. Run DDL in a separate migration phase.
- **Swallowing errors from batch results** — `db.batch()` returns an array; a failed statement sets `results[i].success = false` but does not throw. Always check `result.success` for each entry.
- **Relying on `meta.changes === 1` without also checking `result.success`** — a statement can succeed (`success: true`) with `changes: 0` if a `WHERE` clause matched nothing; this is not an error from D1's perspective but may be a logic error from yours.
- **Reading data to confirm a write in the same request context** — D1 reads after writes within the same Worker invocation may be served from a read replica that hasn't yet received the write. Use `SELECT` inside the same transaction for consistency.

---

## Gotchas

- D1 is built on SQLite but runs remotely. Network timeouts during a long-running `exec()` may leave the server-side transaction open until it times out on D1's side (typically a few seconds); the client will see a network error but the transaction state on D1 is indeterminate until the server-side timeout fires.
- `ROLLBACK` outside of an active transaction throws a D1 error (`cannot rollback - no transaction is active`). Catch this specifically when issuing a defensive rollback in error handlers.
- D1 does not support `SAVEPOINT` in all configurations; nested transaction emulation via savepoints may silently fail.
- The `meta.duration` field in `D1Result` reflects server-side execution time, not round-trip latency. High duration with low round-trip time indicates a slow query; high round-trip with low duration indicates network overhead.
- `db.exec()` does not support binding parameters (only raw SQL strings). Never interpolate user input into `exec()` — always use `db.prepare().bind()` for user-controlled values.

---

## Verification

1. Write a test (Step 6) that deliberately triggers a constraint failure mid-transaction. Confirm the consistency check (Step 4) returns `consistent: true` after the failed attempt.
2. Enable D1's query logging in `wrangler.toml` (`[observability] enabled = true`) and inspect the query log to confirm `BEGIN`/`COMMIT`/`ROLLBACK` appear as expected.
3. Deploy the meta-logger (Step 5) to staging and run the operation manually. Verify `changes` counts match expected row mutations.
4. Introduce an artificial network timeout (e.g., `signal: AbortSignal.timeout(100)`) and confirm the rollback path fires and leaves no partial state.

---

## Related

- `d1-column-affinity-gotcha.md`
- `d1-integer-overflow-javascript.md`
- `d1-env-type-incompatibility.md`

---

## Sources

- Cloudflare D1 — Transactions: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- Cloudflare D1 — D1Database API: https://developers.cloudflare.com/d1/worker-api/d1-database/
- SQLite Transaction documentation: https://www.sqlite.org/lang_transaction.html
- Cloudflare Workers Vitest integration: https://developers.cloudflare.com/workers/testing/vitest-integration/
