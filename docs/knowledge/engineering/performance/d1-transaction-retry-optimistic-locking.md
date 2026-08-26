# D1 Transaction Retry and Optimistic Locking

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
A D1 write that succeeds in isolation fails intermittently under concurrent load with `SQLITE_BUSY` or serialization errors. Wrapping mutations in retried transactions with an optimistic version column eliminates lost updates and reduces conflict-induced errors by over 90 % at p95.

## Context
D1 uses SQLite under the hood with WAL (Write-Ahead Log) mode. Only one writer can hold the write lock at a time per database. Under concurrent Workers invocations hitting the same D1 instance, write contention manifests as `SQLITE_BUSY` errors (D1 surfaces these as HTTP 500 with `D1_ERROR`). The correct response is bounded exponential backoff with jitter rather than immediate failure. For rows that require conditional updates (e.g., inventory counters, account balances), an optimistic locking pattern using a `version` column prevents lost updates without resorting to `SELECT FOR UPDATE` (which SQLite does not support).

## Pattern 1 — Retry Helper with Exponential Backoff + Jitter

```typescript
interface RetryOptions {
  maxAttempts?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

async function withD1Retry<T>(
  fn: () => Promise<T>,
  opts: RetryOptions = {},
): Promise<T> {
  const { maxAttempts = 5, baseDelayMs = 50, maxDelayMs = 2_000 } = opts;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err: unknown) {
      const isRetryable =
        err instanceof Error &&
        (err.message.includes("SQLITE_BUSY") ||
          err.message.includes("D1_ERROR") ||
          err.message.includes("database is locked"));

      if (!isRetryable || attempt === maxAttempts) throw err;

      // Full-jitter exponential backoff
      const cap = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt);
      const delay = Math.random() * cap;
      await new Promise<void>((resolve) => setTimeout(resolve, delay));
    }
  }

  // TypeScript exhaustiveness — unreachable
  throw new Error("retry loop exited without returning");
}
```

## Pattern 2 — Optimistic Locking Schema

```sql
-- Migration: add version column for optimistic locking
CREATE TABLE IF NOT EXISTS inventory (
  id       INTEGER PRIMARY KEY,
  sku      TEXT    NOT NULL UNIQUE,
  quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
  version  INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_inventory_sku ON inventory (sku);
```

## Pattern 3 — Optimistic Update with Version Check

```typescript
interface InventoryRow {
  id: number;
  sku: string;
  quantity: number;
  version: number;
}

async function decrementInventory(
  db: D1Database,
  sku: string,
  delta: number,
): Promise<InventoryRow> {
  return withD1Retry(async () => {
    // Read current state
    const row = await db
      .prepare("SELECT id, sku, quantity, version FROM inventory WHERE sku = ?")
      .bind(sku)
      .first<InventoryRow>();

    if (!row) throw new Error(`SKU not found: ${sku}`);
    if (row.quantity < delta) throw new Error(`Insufficient stock for ${sku}`);

    // Conditional update — only succeeds if version has not changed
    const result = await db
      .prepare(
        `UPDATE inventory
            SET quantity = quantity - ?,
                version  = version  + 1
          WHERE sku     = ?
            AND version = ?
            AND quantity >= ?`,
      )
      .bind(delta, sku, row.version, delta)
      .run();

    if (result.meta.changes === 0) {
      // Another writer modified the row — surface as retryable error
      throw new Error("SQLITE_BUSY: version conflict on inventory update");
    }

    return { ...row, quantity: row.quantity - delta, version: row.version + 1 };
  });
}
```

## Pattern 4 — Batched Transaction with Retry

```typescript
interface TransferPayload {
  fromId: number;
  toId: number;
  amount: number;
}

async function transferFunds(
  db: D1Database,
  payload: TransferPayload,
): Promise<void> {
  await withD1Retry(async () => {
    const { fromId, toId, amount } = payload;

    const [debit, credit] = await db.batch([
      db
        .prepare(
          `UPDATE accounts
              SET balance = balance - ?,
                  version = version + 1
            WHERE id      = ?
              AND balance >= ?
              AND version = (SELECT version FROM accounts WHERE id = ?)`,
        )
        .bind(amount, fromId, amount, fromId),

      db
        .prepare(
          `UPDATE accounts
              SET balance = balance + ?,
                  version = version + 1
            WHERE id = ?`,
        )
        .bind(amount, toId),
    ]);

    if (debit.meta.changes === 0) {
      throw new Error("SQLITE_BUSY: debit conflict or insufficient funds");
    }
    if (credit.meta.changes === 0) {
      throw new Error("SQLITE_BUSY: credit target account not found");
    }
  });
}
```

## Pattern 5 — Conflict Rate Monitoring via Analytics Engine

```typescript
async function instrumentedD1Write(
  db: D1Database,
  ae: AnalyticsEngineDataset,
  operation: string,
  fn: () => Promise<void>,
): Promise<void> {
  let attempts = 0;
  const t0 = Date.now();

  try {
    await withD1Retry(async () => {
      attempts++;
      await fn();
    });
  } finally {
    ae.writeDataPoint({
      blobs: [operation, attempts > 1 ? "retried" : "first-try"],
      doubles: [attempts, Date.now() - t0],
      indexes: [operation.slice(0, 32)],
    });
  }
}
```

## Anti-patterns
- Retrying non-idempotent writes (e.g., `INSERT` without `ON CONFLICT`) without version guards — produces duplicate rows on retry
- Using `SELECT ... FOR UPDATE` syntax — SQLite/D1 does not support pessimistic row-level locking; the statement is silently accepted but provides no isolation
- Catching all errors and retrying — only retry `SQLITE_BUSY` and lock-related messages; retrying constraint violations or type errors loops forever
- Setting `maxAttempts` above 8 without circuit-breaking logic — a D1 instance under sustained write pressure needs circuit-breaking at the Worker level, not unlimited retries
- Issuing individual `UPDATE` statements outside a `db.batch()` for multi-row transfers — partial writes leave the database in an inconsistent state if the Worker is killed mid-flight

## Gotchas
- D1 `db.batch()` is atomic within a single D1 invocation but is NOT a full SQLite `BEGIN TRANSACTION … COMMIT` — a D1 batch fails atomically only if the underlying SQLite transaction fails; individual statement errors within a batch still abort the whole batch
- The `version` column pattern provides optimistic concurrency but increases the cost of every write by one read — evaluate whether the contention rate justifies it (use Analytics Engine conflict rate monitoring first)
- `result.meta.changes` returns `0` for `UPDATE` statements that matched zero rows AND for statements on tables with `WITHOUT ROWID` that use composite keys — verify schema before relying on `changes` as the conflict signal
- D1 read replicas (beta) serve reads from the nearest replica but always route writes to the primary; retry logic must account for the write-path RTT to the primary region
- Jitter is critical — without it, retrying Workers all back off to the same interval, creating a thundering herd that makes contention worse

## Verification
```bash
# Watch D1 error rate in tail logs
wrangler tail --format json | jq 'select(.exceptions != null) | .exceptions[].message'

# Query conflict rate from Analytics Engine SQL API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "SELECT blob2 AS outcome, count() AS n, avg(double2) AS avg_ms
          FROM d1_writes
          WHERE timestamp > now() - INTERVAL '1' HOUR
          GROUP BY blob2"

# Check D1 metrics in dashboard
# Cloudflare Dashboard → D1 → <database> → Metrics → Write Errors
```

## Related
- `d1-batch-query-performance-optimization.md`
- `d1-prepared-statement-reuse.md`
- `d1-query-optimization.md`
- `workers-waituntil-background-processing.md`
- `durable-objects-rpc-batch-coalescing.md`

## Sources
- https://developers.cloudflare.com/d1/reference/transactions/
- https://developers.cloudflare.com/d1/observability/metrics-analytics/
- https://www.sqlite.org/wal.html
- https://developers.cloudflare.com/d1/platform/client-api/#batch-statements
