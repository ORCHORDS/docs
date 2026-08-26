# D1 Composite Unique Constraints and Conditional Upserts

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to enforce uniqueness across two or more columns together (e.g., a
user can only have one active subscription per plan, or a product can only
appear once per cart), and you want idiomatic upsert behaviour when a conflict
on that composite key occurs — updating specific columns while leaving others
untouched.

## Context

SQLite (and therefore D1) supports composite UNIQUE constraints both inline at
table-creation time and as standalone `CREATE UNIQUE INDEX` statements. These
behave identically for conflict detection. `INSERT OR REPLACE`, `INSERT OR
IGNORE`, and `ON CONFLICT DO UPDATE` (PostgreSQL-style upsert syntax, available
in SQLite 3.24+) all interact with composite constraints.

D1 runs on SQLite 3.x with `ON CONFLICT DO UPDATE` support available.

---

## Defining Composite UNIQUE Constraints

### Table-level constraint (preferred for multi-column):

```sql
CREATE TABLE cart_items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  cart_id     TEXT    NOT NULL,
  product_id  TEXT    NOT NULL,
  quantity    INTEGER NOT NULL DEFAULT 1,
  added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (cart_id, product_id)
);
```

### Via a separate unique index (equivalent, more flexible):

```sql
CREATE TABLE cart_items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  cart_id    TEXT    NOT NULL,
  product_id TEXT    NOT NULL,
  quantity   INTEGER NOT NULL DEFAULT 1,
  added_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX ux_cart_items_cart_product
  ON cart_items (cart_id, product_id);
```

Both approaches make `(cart_id, product_id)` a conflict target for upserts.

---

## Upsert on Composite Conflict: `ON CONFLICT DO UPDATE`

```typescript
// Add to cart, incrementing quantity if item already exists
async function addToCart(
  db: D1Database,
  cartId: string,
  productId: string,
  qty: number
): Promise<void> {
  await db.prepare(`
    INSERT INTO cart_items (cart_id, product_id, quantity)
    VALUES (?, ?, ?)
    ON CONFLICT (cart_id, product_id)
    DO UPDATE SET
      quantity = quantity + excluded.quantity,
      added_at = datetime('now')
  `).bind(cartId, productId, qty).run();
}
```

`excluded` refers to the values that *would have been inserted* — the standard
SQLite/PostgreSQL upsert alias.

---

## `ON CONFLICT DO NOTHING` — Idempotent Inserts

```typescript
// Ensure a membership record exists; skip if already present
async function ensureMembership(
  db: D1Database,
  userId: string,
  orgId: string,
  role: string
): Promise<void> {
  await db.prepare(`
    INSERT INTO memberships (user_id, org_id, role)
    VALUES (?, ?, ?)
    ON CONFLICT (user_id, org_id) DO NOTHING
  `).bind(userId, orgId, role).run();
}
```

---

## Conditional Upsert — Only Update When a Condition Is Met

Prevent stale data from overwriting newer data using a WHERE clause on the
`DO UPDATE`:

```sql
CREATE TABLE inventory (
  sku         TEXT NOT NULL,
  warehouse   TEXT NOT NULL,
  quantity    INTEGER NOT NULL,
  updated_at  TEXT NOT NULL,
  UNIQUE (sku, warehouse)
);
```

```typescript
// Only update inventory if the incoming record is newer
async function syncInventory(
  db: D1Database,
  sku: string,
  warehouse: string,
  qty: number,
  updatedAt: string
): Promise<void> {
  await db.prepare(`
    INSERT INTO inventory (sku, warehouse, quantity, updated_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (sku, warehouse)
    DO UPDATE SET
      quantity   = excluded.quantity,
      updated_at = excluded.updated_at
    WHERE excluded.updated_at > inventory.updated_at
  `).bind(sku, warehouse, qty, updatedAt).run();
}
```

When the WHERE clause evaluates to false, D1 silently skips the update — no
error is raised.

---

## Returning the Upserted Row

Use the `RETURNING` clause (SQLite 3.35+, supported in D1) to get back the
final row state regardless of whether an insert or update occurred:

```typescript
interface CartItem {
  id: number;
  cart_id: string;
  product_id: string;
  quantity: number;
}

async function upsertCartItem(
  db: D1Database,
  cartId: string,
  productId: string,
  qty: number
): Promise<CartItem> {
  const result = await db.prepare(`
    INSERT INTO cart_items (cart_id, product_id, quantity)
    VALUES (?, ?, ?)
    ON CONFLICT (cart_id, product_id)
    DO UPDATE SET quantity = quantity + excluded.quantity
    RETURNING id, cart_id, product_id, quantity
  `).bind(cartId, productId, qty).first<CartItem>();

  if (!result) throw new Error("Upsert returned no row");
  return result;
}
```

---

## Batch Upserts with `db.batch()`

```typescript
interface StockUpdate {
  sku: string;
  warehouse: string;
  qty: number;
  updatedAt: string;
}

async function batchSyncInventory(
  db: D1Database,
  updates: StockUpdate[]
): Promise<void> {
  const stmt = db.prepare(`
    INSERT INTO inventory (sku, warehouse, quantity, updated_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (sku, warehouse)
    DO UPDATE SET
      quantity   = excluded.quantity,
      updated_at = excluded.updated_at
    WHERE excluded.updated_at > inventory.updated_at
  `);

  await db.batch(
    updates.map(u => stmt.bind(u.sku, u.warehouse, u.qty, u.updatedAt))
  );
}
```

`db.batch()` runs all statements atomically in a single HTTP round-trip.

---

## NULL Handling in Composite Unique Constraints

SQLite treats NULL as distinct from every other NULL in UNIQUE constraints
(per SQL standard). Two rows with `(cart_id=NULL, product_id='x')` do **not**
conflict.

```typescript
// Safe to insert multiple rows with NULL cart_id — no UNIQUE violation
await db.batch([
  db.prepare("INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (NULL, 'x', 1)"),
  db.prepare("INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (NULL, 'x', 1)"),
]);
```

If you need NULL to be treated as a single value, use a partial index or a
sentinel constant (`''`, `'__null__'`) instead of SQL NULL.

---

## Anti-patterns

- **`INSERT OR REPLACE` on a table with a composite unique index**: this
  performs a DELETE + INSERT, which changes the `id` (AUTOINCREMENT) and
  cascades DELETEs on FK-dependent rows. Prefer `ON CONFLICT DO UPDATE`.
- **Defining the conflict target as the wrong subset of columns**: if you have
  `UNIQUE(a, b, c)` but write `ON CONFLICT (a, b)`, SQLite will not match the
  constraint and will raise a UNIQUE constraint error.
- **Forgetting to list all columns in the conflict target**: `ON CONFLICT`
  requires the exact column list matching a UNIQUE constraint or index; a
  partial list raises a parse error.
- **Using composite UNIQUE where a single surrogate key would suffice**: only
  use composite UNIQUE when the combination itself has business meaning.

---

## Gotchas

- You must name every column of the composite constraint in the
  `ON CONFLICT (...)` clause. SQLite does not support `ON CONFLICT ON
  CONSTRAINT <name>` syntax (that is a PostgreSQL feature).
- `DO UPDATE SET ... WHERE` skips the update silently when the WHERE is false;
  `meta.changes` in the D1 result will be `0`. Check this if callers need to
  distinguish insert vs. update vs. no-op.
- A `UNIQUE` constraint defined with `WITHOUT ROWID` tables has different
  internal B-tree representation but identical SQL semantics.
- `db.batch()` is atomic across all statements; a conflict-error in one
  statement that is not handled by `ON CONFLICT` rolls back the entire batch.

---

## Verification

```typescript
// Verify upsert increments quantity on conflict
await env.DB.prepare(
  "INSERT OR IGNORE INTO cart_items (cart_id, product_id, quantity) VALUES ('c1','p1',1)"
).run();
await upsertCartItem(env.DB, "c1", "p1", 3);
const row = await env.DB.prepare(
  "SELECT quantity FROM cart_items WHERE cart_id='c1' AND product_id='p1'"
).first<{ quantity: number }>();
console.assert(row?.quantity === 4, "Expected quantity 4 after upsert");
```

---

## Related

- `d1-upsert-conflict-resolution-workers.md`
- `d1-returning-clause-upsert-workers.md`
- `d1-batch-operations-performance.md`
- `d1-foreign-key-on-delete-cascade-workers.md`
- `unique-constraints.md`

---

## Sources

- SQLite ON CONFLICT clause: https://www.sqlite.org/lang_conflict.html
- SQLite upsert (ON CONFLICT DO UPDATE): https://www.sqlite.org/lang_upsert.html
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite RETURNING clause: https://www.sqlite.org/lang_returning.html
