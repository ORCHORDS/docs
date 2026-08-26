# D1 Savepoint Nested Transaction Pattern in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Worker executes a multi-step write operation where individual steps may fail independently, but you need to roll back only the failing sub-step rather than the entire transaction. Wrapping everything in a single `BEGIN/COMMIT` block loses too much work on partial failures. You want partial rollback and retry semantics inside a single D1 database call batch.

## Context

SQLite supports **SAVEPOINTs**, which are named checkpoints within a transaction. A `ROLLBACK TO SAVEPOINT name` undoes work since that savepoint without aborting the outer transaction. `RELEASE SAVEPOINT name` commits the sub-transaction into the outer transaction. D1 exposes this through `db.batch()`, which sends multiple statements atomically to the same SQLite connection. Savepoints are the correct mechanism for nested transaction logic in D1 — nested `BEGIN` calls are not valid in SQLite and will error.

---

## 1. Savepoint Basics in SQLite

```sql
BEGIN;
  SAVEPOINT step_a;
    INSERT INTO audit_log (event) VALUES ('a');
  RELEASE SAVEPOINT step_a;   -- commits step_a into outer txn

  SAVEPOINT step_b;
    INSERT INTO orders (id) VALUES ('bad-data');
  ROLLBACK TO SAVEPOINT step_b; -- undoes step_b only
  RELEASE SAVEPOINT step_b;     -- removes the savepoint marker

COMMIT; -- commits step_a, step_b insert never happened
```

---

## 2. D1 Batch with Savepoints

`db.batch()` runs all statements on one connection in order. Embed savepoint SQL as raw statements between your data operations.

```typescript
// workers/src/db/savepoint.ts
export async function withSavepoint<T>(
  db: D1Database,
  name: string,
  stmts: D1PreparedStatement[],
): Promise<D1Result[]> {
  const sp = name.replace(/\W/g, '_'); // sanitize savepoint name

  const results = await db.batch([
    db.prepare(`SAVEPOINT ${sp}`),
    ...stmts,
    db.prepare(`RELEASE SAVEPOINT ${sp}`),
  ]);

  return results;
}

export async function rollbackSavepoint(
  db: D1Database,
  name: string,
): Promise<D1Result[]> {
  const sp = name.replace(/\W/g, '_');
  return db.batch([
    db.prepare(`ROLLBACK TO SAVEPOINT ${sp}`),
    db.prepare(`RELEASE SAVEPOINT ${sp}`),
  ]);
}
```

---

## 3. Multi-step Order Fulfillment with Partial Rollback

```typescript
// workers/src/handlers/fulfill-order.ts
import type { D1Database } from '@cloudflare/workers-types';

interface FulfillResult {
  orderId: string;
  inventoryReserved: boolean;
  invoiceCreated: boolean;
  notificationQueued: boolean;
}

export async function fulfillOrder(
  db: D1Database,
  orderId: string,
  userId: string,
  items: Array<{ sku: string; qty: number }>,
): Promise<FulfillResult> {
  const result: FulfillResult = {
    orderId,
    inventoryReserved: false,
    invoiceCreated: false,
    notificationQueued: false,
  };

  // Outer transaction wraps all steps
  const inventoryStmts = items.map(({ sku, qty }) =>
    db.prepare(
      `UPDATE inventory SET reserved = reserved + ? WHERE sku = ? AND available >= ?`
    ).bind(qty, sku, qty)
  );

  try {
    // Step 1: reserve inventory — safe to retry if it fails
    await db.batch([
      db.prepare('SAVEPOINT reserve_inventory'),
      ...inventoryStmts,
      db.prepare('RELEASE SAVEPOINT reserve_inventory'),
    ]);
    result.inventoryReserved = true;
  } catch (err) {
    await db.batch([
      db.prepare('ROLLBACK TO SAVEPOINT reserve_inventory'),
      db.prepare('RELEASE SAVEPOINT reserve_inventory'),
    ]);
    // Continue — we skip invoice if inventory failed
    return result;
  }

  try {
    // Step 2: create invoice — independent of notification step
    await db.batch([
      db.prepare('SAVEPOINT create_invoice'),
      db.prepare(`INSERT INTO invoices (order_id, user_id, created_at) VALUES (?, ?, unixepoch())`)
        .bind(orderId, userId),
      db.prepare('RELEASE SAVEPOINT create_invoice'),
    ]);
    result.invoiceCreated = true;
  } catch {
    await db.batch([
      db.prepare('ROLLBACK TO SAVEPOINT create_invoice'),
      db.prepare('RELEASE SAVEPOINT create_invoice'),
    ]);
    // Invoice failed but inventory is still reserved
  }

  // Step 3: queue notification — best-effort, never rolls back inventory
  try {
    await db.batch([
      db.prepare('SAVEPOINT queue_notification'),
      db.prepare(`INSERT INTO notification_queue (order_id, type, created_at) VALUES (?, 'fulfilled', unixepoch())`)
        .bind(orderId),
      db.prepare('RELEASE SAVEPOINT queue_notification'),
    ]);
    result.notificationQueued = true;
  } catch {
    // Swallow — non-critical path
  }

  return result;
}
```

---

## 4. Savepoint-based Upsert with Conflict Handling

Savepoints enable try/catch semantics for constraint violations without aborting the outer transaction.

```typescript
// workers/src/db/safe-upsert.ts
export async function safeUpsertUser(
  db: D1Database,
  user: { id: string; email: string; name: string },
  outerBatch: D1PreparedStatement[],
): Promise<{ inserted: boolean }> {
  const sp = 'upsert_user';
  let inserted = false;

  try {
    await db.batch([
      ...outerBatch,
      db.prepare(`SAVEPOINT ${sp}`),
      db.prepare(`INSERT INTO users (id, email, name) VALUES (?, ?, ?)`)
        .bind(user.id, user.email, user.name),
      db.prepare(`RELEASE SAVEPOINT ${sp}`),
    ]);
    inserted = true;
  } catch (err) {
    // UNIQUE constraint on email — fall back to UPDATE
    await db.batch([
      db.prepare(`ROLLBACK TO SAVEPOINT ${sp}`),
      db.prepare(`RELEASE SAVEPOINT ${sp}`),
      db.prepare(`UPDATE users SET name = ? WHERE email = ?`)
        .bind(user.name, user.email),
    ]);
  }

  return { inserted };
}
```

---

## 5. Nested Savepoints (Depth-2)

SQLite supports stacking savepoints by name. Inner savepoints must be released or rolled back before releasing the outer one.

```typescript
// workers/src/db/nested-savepoint.ts
export async function processWithNestedSavepoints(
  db: D1Database,
  parentId: string,
  children: string[],
): Promise<void> {
  const childStmts: D1PreparedStatement[] = [];

  for (const childId of children) {
    const sp = `child_${childId.replace(/\W/g, '')}`;
    // Each child wrapped in its own savepoint — failures are isolated
    childStmts.push(
      db.prepare(`SAVEPOINT ${sp}`),
      db.prepare(`INSERT INTO children (id, parent_id) VALUES (?, ?)`)
        .bind(childId, parentId),
      db.prepare(`RELEASE SAVEPOINT ${sp}`),
    );
  }

  await db.batch([
    db.prepare('SAVEPOINT parent_write'),
    db.prepare(`INSERT INTO parents (id) VALUES (?)`).bind(parentId),
    ...childStmts,
    db.prepare('RELEASE SAVEPOINT parent_write'),
  ]);
}
```

---

## 6. Idempotent Savepoint Wrapper

Use a helper that names savepoints after a request ID to make the entire Worker handler idempotent.

```typescript
// workers/src/db/idempotent-write.ts
export async function idempotentWrite(
  db: D1Database,
  requestId: string,
  stmts: D1PreparedStatement[],
): Promise<boolean> {
  const sp = `req_${requestId.replace(/\W/g, '')}`;

  // Check idempotency key first
  const existing = await db
    .prepare(`SELECT 1 FROM idempotency_keys WHERE key = ?`)
    .bind(requestId)
    .first();
  if (existing) return false; // already processed

  await db.batch([
    db.prepare(`SAVEPOINT ${sp}`),
    db.prepare(`INSERT INTO idempotency_keys (key, created_at) VALUES (?, unixepoch())`)
      .bind(requestId),
    ...stmts,
    db.prepare(`RELEASE SAVEPOINT ${sp}`),
  ]);

  return true;
}
```

---

## Anti-patterns

- **Nested `BEGIN` calls.** SQLite does not support nested `BEGIN`. Use SAVEPOINTs for sub-transaction boundaries.
- **Using `db.exec()` for savepoint SQL.** `db.exec()` does not participate in a batch and runs on a separate logical turn; use `db.prepare('SAVEPOINT x')` inside `db.batch()`.
- **Forgetting `RELEASE` after `ROLLBACK TO`.** `ROLLBACK TO` undoes data changes but leaves the savepoint marker active. Always follow with `RELEASE` to remove the marker and free resources.
- **Dynamic savepoint names from user input.** Savepoint names are SQL identifiers — sanitize them or use a fixed name derived from a hash.
- **Assuming savepoints span multiple batches.** Each `db.batch()` call is one database round-trip. Savepoints started in one batch and released in another are not supported in D1's stateless request model.

---

## Gotchas

- In D1, each `db.batch()` is atomic at the HTTP transport level. If the Worker throws between batches, outer savepoints from a prior batch are already committed or rolled back — they do not persist across batch calls.
- `ROLLBACK TO SAVEPOINT x` does not abort the outer transaction. The outer `COMMIT` (or end of batch) still succeeds.
- Savepoint names are case-insensitive in SQLite; treat them as lowercase identifiers.
- If you use `db.batch()` without explicit `BEGIN/COMMIT`, D1 wraps the batch in an implicit transaction. Savepoints within that batch behave as nested checkpoints inside the implicit transaction.
- D1 does not expose a persistent connection object between Worker invocations, so savepoints cannot span HTTP requests.

---

## Verification

```typescript
// Test that rollback to savepoint preserves outer transaction data
const [sp1, insert1, sp2, insert2, rollback2, release2, commit1] = await db.batch([
  db.prepare('SAVEPOINT outer'),
  db.prepare(`INSERT INTO test_log (msg) VALUES ('outer-write')`),
  db.prepare('SAVEPOINT inner'),
  db.prepare(`INSERT INTO test_log (msg) VALUES ('inner-write')`),
  db.prepare('ROLLBACK TO SAVEPOINT inner'),
  db.prepare('RELEASE SAVEPOINT inner'),
  db.prepare('RELEASE SAVEPOINT outer'),
]);

const rows = await db.prepare(`SELECT msg FROM test_log`).all();
// Expected: [{ msg: 'outer-write' }] — inner-write was rolled back
console.assert(rows.results.length === 1 && rows.results[0].msg === 'outer-write');
```

---

## Related

- `savepoints-nested-transactions.md`
- `d1-batch-operations-performance.md`
- `d1-upsert-conflict-resolution-workers.md`
- `d1-foreign-keys-referential-integrity.md`
- `transaction-isolation-levels.md`
- `idempotency-keys-database.md`

---

## Sources

- https://www.sqlite.org/lang_savepoint.html
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://www.sqlite.org/isolation.html
- https://developers.cloudflare.com/d1/reference/transactions/
