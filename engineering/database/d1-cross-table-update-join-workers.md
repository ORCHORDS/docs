# D1 Cross-Table UPDATE with Subquery in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to update rows in one table using values from another — denormalising a computed field, propagating a price change from `products` into `order_line_items`, or resetting a status based on a join condition. SQLite (and therefore D1) does not support `UPDATE … FROM` (Postgres syntax), so the pattern uses correlated subqueries or `WITH` CTEs instead.

## Context

MySQL and PostgreSQL support `UPDATE t1 SET … FROM t2 WHERE …`, but SQLite requires either a scalar correlated subquery in the `SET` clause or an `EXISTS`/`IN` subquery in the `WHERE` clause. Both patterns are fully supported in D1. For bulk cross-table updates, a batched approach with explicit pagination avoids locking the database for long periods.

---

## Pattern 1: Correlated Subquery in SET Clause

Propagate the current unit price from `products` into every unshipped `order_line_items` row.

```typescript
// update-prices.ts
export async function syncLineItemPrices(db: D1Database): Promise<number> {
  const result = await db
    .prepare(
      `UPDATE order_line_items
          SET unit_price_cents = (
                SELECT price_cents
                  FROM products
                 WHERE products.id = order_line_items.product_id
              )
        WHERE status = 'pending'
          AND EXISTS (
                SELECT 1 FROM products
                 WHERE products.id = order_line_items.product_id
              )`
    )
    .run();
  return result.meta.changes;
}
```

The `EXISTS` guard in `WHERE` prevents setting `unit_price_cents` to `NULL` for rows whose `product_id` no longer exists in `products`.

---

## Pattern 2: CTE-Based Update (Readable Alternative)

```typescript
// cte-update.ts
export async function applyDiscountTier(db: D1Database): Promise<void> {
  // Compute the discount per customer from orders, then write it to customers table
  await db
    .prepare(
      `WITH ranked AS (
          SELECT customer_id,
                 CASE
                   WHEN SUM(total_cents) > 100000 THEN 10
                   WHEN SUM(total_cents) >  50000 THEN  5
                   ELSE 0
                 END AS discount_pct
            FROM orders
           WHERE placed_at >= date('now', '-90 days')
           GROUP BY customer_id
       )
       UPDATE customers
          SET discount_pct = (
                SELECT discount_pct FROM ranked
                 WHERE ranked.customer_id = customers.id
              )
        WHERE id IN (SELECT customer_id FROM ranked)`
    )
    .run();
}
```

---

## Pattern 3: Batched Cross-Table Update for Large Tables

D1 has a 30-second query timeout and a row-change limit per statement. Batch large updates by primary key ranges.

```typescript
// batch-update.ts
export async function batchDenormalise(
  db: D1Database,
  batchSize = 200
): Promise<number> {
  let totalChanges = 0;
  let lastId = 0;

  while (true) {
    // Collect the next batch of candidate IDs
    const candidates = await db
      .prepare(
        `SELECT li.id
           FROM order_line_items li
           JOIN products p ON p.id = li.product_id
          WHERE li.id > ?
            AND li.status = 'pending'
            AND li.unit_price_cents != p.price_cents
          ORDER BY li.id
          LIMIT ?`
      )
      .bind(lastId, batchSize)
      .all<{ id: number }>();

    if (candidates.results.length === 0) break;

    const ids = candidates.results.map(r => r.id);
    const placeholders = ids.map(() => '?').join(', ');

    const result = await db
      .prepare(
        `UPDATE order_line_items
            SET unit_price_cents = (
                  SELECT price_cents FROM products
                   WHERE products.id = order_line_items.product_id
                )
          WHERE id IN (${placeholders})`
      )
      .bind(...ids)
      .run();

    totalChanges += result.meta.changes;
    lastId = ids.at(-1)!;
    if (ids.length < batchSize) break;
  }

  return totalChanges;
}
```

---

## Pattern 4: Conditional Multi-Column Update

Update several columns in one pass using correlated subqueries per column.

```typescript
// multi-col-update.ts
export async function syncInventorySnapshot(db: D1Database): Promise<void> {
  await db
    .prepare(
      `UPDATE inventory_snapshots
          SET
            product_sku   = (SELECT sku         FROM products WHERE id = inventory_snapshots.product_id),
            product_name  = (SELECT name        FROM products WHERE id = inventory_snapshots.product_id),
            category      = (SELECT category    FROM products WHERE id = inventory_snapshots.product_id),
            snapshot_at   = strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE product_id IN (SELECT id FROM products WHERE updated_at > inventory_snapshots.snapshot_at)`
    )
    .run();
}
```

> **Perf note:** Each correlated subquery per column re-executes the `products` lookup. If the subquery is expensive, materialise via a CTE (Pattern 2) or use a `REPLACE INTO … SELECT` instead.

---

## Pattern 5: Replace-Select as an Update Alternative

When updating every column is acceptable, `INSERT OR REPLACE … SELECT` is cleaner than correlated subqueries.

```typescript
// replace-select.ts
export async function refreshProductCache(db: D1Database): Promise<void> {
  // product_cache mirrors products with a refreshed_at timestamp
  await db
    .prepare(
      `INSERT OR REPLACE INTO product_cache
         (id, sku, name, price_cents, refreshed_at)
       SELECT id, sku, name, price_cents, strftime('%Y-%m-%dT%H:%M:%fZ','now')
         FROM products
        WHERE updated_at > (
                SELECT COALESCE(MAX(refreshed_at), '1970-01-01') FROM product_cache
              )`
    )
    .run();
}
```

---

## Anti-patterns

- **Using `UPDATE … FROM` syntax** — this is PostgreSQL / SQL Server syntax and will raise a parse error in SQLite/D1. Always use correlated subqueries or CTEs.
- **Uncorrelated subquery in SET returning multiple rows** — if `SELECT price_cents FROM products` returns more than one row, SQLite raises "sub-select returns N rows — expected 1". Always add `WHERE products.id = outer_table.product_id`.
- **Omitting the EXISTS guard** — a correlated subquery that finds no match returns NULL, silently overwriting a column with NULL.
- **Running unbounded cross-table updates** — without `WHERE` / `LIMIT`, a cross-table update on large tables blocks D1 for the full duration; always add the batching loop.

## Gotchas

- SQLite evaluates each correlated subquery once per updated row; for N rows and M subquery columns you get N×M lookups. Add an index on the join key in the looked-up table (`products.id` is already the PK, so this is usually fine).
- `result.meta.changes` returns the number of rows actually modified, not rows examined — use it to detect no-ops.
- D1 does not support `UPDATE … RETURNING` combined with a `FROM` join in older SQLite builds; use the standalone `RETURNING` clause or a follow-up `SELECT` with the same `WHERE`.
- In `batch` mode the 100-statement limit applies across the batch, not per statement; keep your batch of UPDATEs within that ceiling.

## Verification

```typescript
async function smokeTest(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare("INSERT OR REPLACE INTO products (id,sku,price_cents) VALUES (1,'A',500)"),
    db.prepare("INSERT OR REPLACE INTO order_line_items (id,product_id,unit_price_cents,status) VALUES (10,1,400,'pending')"),
  ]);

  const { syncLineItemPrices } = await import('./update-prices');
  const changed = await syncLineItemPrices(db);

  const row = await db
    .prepare('SELECT unit_price_cents FROM order_line_items WHERE id = 10')
    .first<{ unit_price_cents: number }>();

  console.assert(changed === 1, 'One row should have been updated');
  console.assert(row?.unit_price_cents === 500, 'Price should match products table');
}
```

## Related

- `d1-batch-operations-performance.md`
- `d1-upsert-conflict-resolution-workers.md`
- `d1-returning-clause-upsert-workers.md`
- `d1-exists-vs-in-subquery-performance.md`
- `d1-materialized-view-simulation-cron.md`
- `cte-common-table-expressions.md`

## Sources

- SQLite UPDATE documentation: https://www.sqlite.org/lang_update.html
- SQLite correlated subqueries: https://www.sqlite.org/lang_select.html
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
