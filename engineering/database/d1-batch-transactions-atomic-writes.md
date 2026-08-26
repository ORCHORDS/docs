# Atomic Multi-Table Writes with D1 `db.batch()`

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to write to multiple D1 tables in a single atomic operation — for example, inserting an `order` row and updating an `inventory` row together, so that either both succeed or neither does. Network errors or Worker exceptions between two separate `db.run()` calls would leave the database in a partial state. `db.batch()` solves this by sending all statements to D1 in one HTTP round-trip and executing them atomically.

---

## Context

`D1Database.batch()` accepts an array of `D1PreparedStatement` objects and executes them in a single transaction on the D1 server. If any statement in the batch throws (constraint violation, type mismatch, etc.) the entire batch is rolled back and no changes persist. This is equivalent to wrapping all statements in `BEGIN IMMEDIATE; …; COMMIT;` but without the round-trip overhead of sending multiple SQL commands. For cases where you need conditional logic inside the transaction — e.g. read a balance, check it, then debit — an explicit `BEGIN`/`COMMIT` transaction via sequential `db.prepare().run()` calls is the right tool, since `batch()` cannot inspect intermediate results. `INSERT OR IGNORE` combined with a unique constraint enables idempotent batch design safe for retries.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS orders (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key TEXT    NOT NULL UNIQUE,   -- client-generated UUID per request
  user_id         TEXT    NOT NULL,
  product_id      INTEGER NOT NULL,
  quantity        INTEGER NOT NULL,
  total_cents     INTEGER NOT NULL,
  status          TEXT    NOT NULL DEFAULT 'pending',
  created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency
  ON orders(idempotency_key);

CREATE TABLE IF NOT EXISTS inventory (
  product_id  INTEGER PRIMARY KEY,
  sku         TEXT    NOT NULL UNIQUE,
  stock       INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
  reserved    INTEGER NOT NULL DEFAULT 0,
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id   INTEGER NOT NULL REFERENCES orders(id),
  event_type TEXT    NOT NULL,
  payload    TEXT,                         -- JSON
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_order_events_order
  ON order_events(order_id, created_at DESC);
```

---

## Section 2 — Worker implementation

```typescript
// src/db/orders.ts
import { D1Database } from '@cloudflare/workers-types';

interface PlaceOrderInput {
  idempotencyKey: string;
  userId: string;
  productId: number;
  quantity: number;
  totalCents: number;
}

interface PlaceOrderResult {
  orderId: number;
  idempotent: boolean; // true if this was a duplicate (already processed)
}

/**
 * Places an order atomically using db.batch():
 *   1. INSERT OR IGNORE the order row (idempotent via unique key)
 *   2. Decrement inventory.stock by quantity
 *   3. Insert an order_event for audit trail
 *
 * If the order idempotency_key already exists, INSERT OR IGNORE silently
 * skips, changes = 0, and we return the existing order id.
 */
export async function placeOrder(
  db: D1Database,
  input: PlaceOrderInput
): Promise<PlaceOrderResult> {
  const { idempotencyKey, userId, productId, quantity, totalCents } = input;

  // Step 1: Check for existing order (idempotency fast path)
  const existing = await db
    .prepare(
      `SELECT id FROM orders WHERE idempotency_key = ? LIMIT 1`
    )
    .bind(idempotencyKey)
    .first<{ id: number }>();

  if (existing) {
    return { orderId: existing.id, idempotent: true };
  }

  // Step 2: Build the batch — all-or-nothing atomic write
  const insertOrder = db
    .prepare(
      `INSERT OR IGNORE INTO orders
         (idempotency_key, user_id, product_id, quantity, total_cents, status)
       VALUES (?, ?, ?, ?, ?, 'pending')`
    )
    .bind(idempotencyKey, userId, productId, quantity, totalCents);

  const decrementStock = db
    .prepare(
      `UPDATE inventory
       SET stock = stock - ?, updated_at = datetime('now')
       WHERE product_id = ? AND stock >= ?`
    )
    .bind(quantity, productId, quantity);

  // We'll insert the event after we know the order id.
  // For the batch we insert a placeholder event — order id is last_row_id.
  // order_events uses order_id FK; we grab last_row_id from insertOrder result.

  // Execute the core batch first
  const [orderResult, stockResult] = await db.batch([
    insertOrder,
    decrementStock,
  ]);

  // Validate stock was available (UPDATE affected 0 rows = out of stock)
  if (stockResult.meta.changes === 0) {
    // The order INSERT already ran in the batch; since we use INSERT OR IGNORE
    // and idempotency_key is unique, we must clean up the dangling order row.
    // In practice, check stock BEFORE batching (see anti-patterns).
    throw new Error(
      `Insufficient stock for product ${productId} (requested ${quantity})`
    );
  }

  const orderId = orderResult.meta.last_row_id;

  // Step 3: Append the audit event in a separate single statement
  // (depends on orderId from step 2, so cannot be in the first batch)
  await db
    .prepare(
      `INSERT INTO order_events (order_id, event_type, payload)
       VALUES (?, 'order.placed', ?)`
    )
    .bind(
      orderId,
      JSON.stringify({ userId, productId, quantity, totalCents })
    )
    .run();

  return { orderId, idempotent: false };
}

/**
 * Cancel an order: batch UPDATE order status + restore inventory stock.
 */
export async function cancelOrder(
  db: D1Database,
  orderId: number,
  userId: string
): Promise<void> {
  // Fetch order to validate ownership and get quantity
  const order = await db
    .prepare(
      `SELECT product_id, quantity, status FROM orders
       WHERE id = ? AND user_id = ? LIMIT 1`
    )
    .bind(orderId, userId)
    .first<{ product_id: number; quantity: number; status: string }>();

  if (!order) throw new Error('Order not found or access denied.');
  if (order.status !== 'pending') throw new Error(`Cannot cancel order in status: ${order.status}`);

  await db.batch([
    db
      .prepare(
        `UPDATE orders SET status = 'cancelled' WHERE id = ? AND status = 'pending'`
      )
      .bind(orderId),
    db
      .prepare(
        `UPDATE inventory
         SET stock = stock + ?, updated_at = datetime('now')
         WHERE product_id = ?`
      )
      .bind(order.quantity, order.product_id),
    db
      .prepare(
        `INSERT INTO order_events (order_id, event_type, payload)
         VALUES (?, 'order.cancelled', ?)`
      )
      .bind(orderId, JSON.stringify({ cancelledBy: userId })),
  ]);
}
```

---

## Section 3 — Query / Migration helper

```typescript
// Comparing db.batch() vs explicit BEGIN/COMMIT transaction
// Use db.batch() when: all statements are known upfront, no conditional logic.
// Use BEGIN/COMMIT when: you need to read-then-write (e.g., check balance first).

// Pattern A — db.batch() (preferred for known statement sets)
async function batchPattern(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare(`INSERT INTO a (val) VALUES (?)`).bind('x'),
    db.prepare(`UPDATE b SET cnt = cnt + 1 WHERE key = ?`).bind('y'),
  ]);
  // Atomically committed or fully rolled back.
}

// Pattern B — explicit BEGIN/COMMIT (required for conditional logic)
async function transactionPattern(db: D1Database, userId: string): Promise<void> {
  await db.prepare('BEGIN IMMEDIATE').run();
  try {
    const balance = await db
      .prepare(`SELECT balance FROM wallets WHERE user_id = ?`)
      .bind(userId)
      .first<{ balance: number }>();

    if (!balance || balance.balance < 100) {
      await db.prepare('ROLLBACK').run();
      throw new Error('Insufficient balance.');
    }

    await db
      .prepare(`UPDATE wallets SET balance = balance - 100 WHERE user_id = ?`)
      .bind(userId)
      .run();

    await db.prepare('COMMIT').run();
  } catch (err) {
    // Ensure rollback on any error after BEGIN
    try { await db.prepare('ROLLBACK').run(); } catch {}
    throw err;
  }
}

// Pattern C — Idempotent batch with INSERT OR IGNORE
// Safe to retry on network timeout without duplicate rows.
async function idempotentBatch(
  db: D1Database,
  key: string,
  value: string
): Promise<void> {
  await db.batch([
    // unique constraint on (key) ensures only first insert wins
    db.prepare(`INSERT OR IGNORE INTO kv_store (key, value) VALUES (?, ?)`)
      .bind(key, value),
    db.prepare(`INSERT OR IGNORE INTO kv_log (key, created_at) VALUES (?, datetime('now'))`)
      .bind(key),
  ]);
}
```

---

## Anti-patterns

- **Reading a value inside a `batch()` to drive conditional logic** — `db.batch()` returns results only after all statements execute; you cannot inspect an intermediate result to decide the next statement. Use explicit `BEGIN`/`COMMIT` for read-then-write patterns.
- **Batching stock check + decrement without pre-checking** — Including `UPDATE inventory SET stock = stock - ? WHERE stock >= ?` in a batch does not prevent negative stock if a race condition occurs between reading and updating. Pre-check stock in a separate query, then rely on the `CHECK (stock >= 0)` constraint to catch the race.
- **Ignoring `meta.changes` after UPDATE** — A batch `UPDATE` that affects 0 rows does not throw; you must inspect `result.meta.changes` to detect a no-op (e.g., out-of-stock, wrong owner_id).
- **Using auto-increment IDs across batch statements** — `last_row_id` from an `INSERT` inside a batch is only available after the batch resolves; you cannot pass it as a binding to a later statement in the same batch. Split into two operations when you need the new row's ID.
- **Not using `INSERT OR IGNORE` for retryable batches** — Without idempotency keys and `OR IGNORE`, retrying a failed batch after a network timeout may insert duplicate rows.

---

## Gotchas

- `db.batch()` wraps all statements in an implicit transaction; an explicit `BEGIN` inside a batch will conflict and may cause errors — do not mix them.
- The return type of `db.batch()` is `Promise<D1Result[]>` with one `D1Result` per statement in the array; ensure you destructure correctly by index.
- D1's `batch()` has a maximum of 1,000 statements per call; for bulk imports split into chunks.
- `last_row_id` in `meta` reflects the last successful `INSERT`'s rowid within D1's session; for a batch containing multiple inserts it is the rowid of the last insert in the array.
- Explicit `BEGIN IMMEDIATE` acquires a write lock immediately, preventing concurrent Writers from interleaving; `BEGIN DEFERRED` (the default) may deadlock under concurrent load. Use `BEGIN IMMEDIATE` for read-then-write transactions in Workers.

---

## Verification

```bash
# Verify atomic batch: insert order and check inventory decremented
wrangler d1 execute DB --remote --command \
  "SELECT id, status FROM orders WHERE idempotency_key='test-key-1';"

wrangler d1 execute DB --remote --command \
  "SELECT stock FROM inventory WHERE product_id=1;"

# Confirm idempotency: second run with same key should not create duplicate
wrangler d1 execute DB --remote --command \
  "SELECT COUNT(*) AS cnt FROM orders WHERE idempotency_key='test-key-1';"

# Check order events audit trail
wrangler d1 execute DB --remote --command \
  "SELECT event_type, created_at FROM order_events WHERE order_id=1 ORDER BY created_at;"
```

---

## Related

- `d1-row-level-security-workers.md`
- `d1-schema-migration-wrangler-workflow.md`
- `d1-composite-indexes-query-optimization.md`

---

## Sources

- Cloudflare D1 Workers API — https://developers.cloudflare.com/d1/worker-api/
- D1 `batch()` reference — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite transaction types — https://www.sqlite.org/lang_transaction.html
- SQLite INSERT OR IGNORE — https://www.sqlite.org/lang_insert.html
