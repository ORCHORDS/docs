# D1 EXISTS vs IN Subquery Performance

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A D1 query that filters rows using an `IN (SELECT …)` subquery is slower than expected, or EXPLAIN QUERY PLAN shows an unexpected full-table scan. You want to understand when `EXISTS`, `IN`, or a `JOIN` is the right tool for membership tests in D1/SQLite, and how to verify the query planner is choosing an efficient strategy.

---

## Context

SQLite's query planner handles `EXISTS`, `IN (SELECT …)`, and `JOIN` differently depending on whether indexes are available and whether the subquery is correlated:

- **`IN (list)`** — Materialises the value list into a temporary B-tree; fast for small literal lists.
- **`IN (SELECT …)`** — SQLite may materialise the subquery result into a temporary table, then probe that table. With a good index on the outer table it can be efficient; without one it degrades to O(N × M).
- **`EXISTS (SELECT 1 …)`** — Runs the subquery once per outer row, but stops at the first match (`LIMIT 1` semantics). For correlated subqueries this can be faster than `IN` because it short-circuits.
- **`JOIN`** — Usually the most predictable option; the planner has full freedom to choose the join order and use indexes on both sides.

D1 runs SQLite 3.x under the hood. All SQLite query planner behaviour, including `NOT IN` null-trap semantics, applies.

---

## EXISTS vs IN: Basic Comparison

```sql
-- Schema
CREATE TABLE orders (
  id         INTEGER PRIMARY KEY,
  customer_id TEXT NOT NULL,
  status     TEXT NOT NULL
);
CREATE INDEX idx_orders_customer ON orders (customer_id);

CREATE TABLE vip_customers (
  customer_id TEXT PRIMARY KEY,
  tier        TEXT NOT NULL
);
```

```typescript
// src/queries/membership.ts
import type { D1Database } from '@cloudflare/workers-types';

// Option A: IN subquery — materialises vip_customers into a temp set
export async function getVipOrdersIN(db: D1Database) {
  return db
    .prepare(
      `SELECT id, customer_id, status
       FROM orders
       WHERE customer_id IN (SELECT customer_id FROM vip_customers)`
    )
    .all();
}

// Option B: EXISTS — correlated, short-circuits on first match
export async function getVipOrdersEXISTS(db: D1Database) {
  return db
    .prepare(
      `SELECT id, customer_id, status
       FROM orders o
       WHERE EXISTS (
         SELECT 1 FROM vip_customers v
         WHERE v.customer_id = o.customer_id
       )`
    )
    .all();
}

// Option C: JOIN — often fastest, planner picks optimal join order
export async function getVipOrdersJOIN(db: D1Database) {
  return db
    .prepare(
      `SELECT o.id, o.customer_id, o.status
       FROM orders o
       INNER JOIN vip_customers v ON v.customer_id = o.customer_id`
    )
    .all();
}
```

---

## Checking the Query Plan

```typescript
// src/debug/explain.ts
export async function explainQuery(
  db: D1Database,
  sql: string,
  bindings: unknown[] = []
): Promise<string[]> {
  const stmt = db.prepare(`EXPLAIN QUERY PLAN ${sql}`);
  const bound = bindings.reduce(
    (s: D1PreparedStatement, b: unknown) => s.bind(b),
    stmt as unknown as D1PreparedStatement
  );
  const { results } = await (bound as D1PreparedStatement).all<{
    detail: string;
  }>();
  return results.map((r) => r.detail);
}
```

```typescript
// Expected plan for JOIN version (good):
// SCAN orders (using index idx_orders_customer)
// SEARCH vip_customers USING PRIMARY KEY (customer_id=?)

// Warning sign — materialised subquery (potentially slow):
// SCAN orders
// LIST SUBQUERY ...
```

---

## NOT IN vs NOT EXISTS: The Null Trap

`NOT IN` returns no rows if the subquery contains a single `NULL`. `NOT EXISTS` does not have this problem and is the safer choice for exclusion queries.

```typescript
// DANGEROUS: if blocked_customers has any NULL customer_id, returns zero rows
export async function getUnblockedOrdersUnsafe(db: D1Database) {
  return db
    .prepare(
      `SELECT * FROM orders
       WHERE customer_id NOT IN (SELECT customer_id FROM blocked_customers)`
    )
    .all();
}

// SAFE: NOT EXISTS is immune to NULLs in the subquery
export async function getUnblockedOrdersSafe(db: D1Database) {
  return db
    .prepare(
      `SELECT * FROM orders o
       WHERE NOT EXISTS (
         SELECT 1 FROM blocked_customers b
         WHERE b.customer_id = o.customer_id
       )`
    )
    .all();
}
```

---

## Large IN Lists vs EXISTS

For a runtime-generated list of IDs, `IN (?, ?, …)` with a literal list is often faster than a subquery because SQLite constructs a small in-memory B-tree directly from the bound values.

```typescript
// src/queries/bulk.ts
export async function getOrdersByIds(
  db: D1Database,
  orderIds: number[]
): Promise<D1Result> {
  if (orderIds.length === 0) return { results: [], success: true, meta: {} } as unknown as D1Result;

  // Build parameterised IN list — safe, no SQL injection
  const placeholders = orderIds.map(() => '?').join(', ');
  return db
    .prepare(`SELECT * FROM orders WHERE id IN (${placeholders})`)
    .bind(...orderIds)
    .all();
}
```

> D1 has a maximum of 100 variables per statement. Chunk large lists into batches of 100 and use `db.batch()` for parallel execution.

---

## Semi-join Optimisation: EXISTS with LIMIT 1

When the outer query only needs to know whether at least one match exists (not count or retrieve rows), wrap the subquery in `EXISTS` with `SELECT 1` to guarantee early termination:

```typescript
export async function customerHasOrders(
  db: D1Database,
  customerId: string
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT EXISTS (
         SELECT 1 FROM orders WHERE customer_id = ? LIMIT 1
       ) AS has_orders`
    )
    .bind(customerId)
    .first<{ has_orders: number }>();

  return row?.has_orders === 1;
}
```

---

## Anti-patterns

- **`NOT IN` without a `NOT NULL` constraint on the subquery column** — Any `NULL` in the subquery produces a result of `NULL` for every comparison, making the entire `NOT IN` filter return zero rows. Always use `NOT EXISTS` for exclusion logic or add `WHERE column IS NOT NULL` inside the subquery.
- **`IN (SELECT …)` on large, unindexed subquery tables** — SQLite must materialise the full subquery result and build a temporary B-tree. A missing index on the outer join column compounds the problem with a full outer scan.
- **Correlated `EXISTS` with no index on the inner table's join column** — Each outer row triggers a full scan of the inner table. Add an index covering the correlated column.
- **Substituting `IN` for `JOIN` when duplicates matter** — An `INNER JOIN` returns one row per match; if `vip_customers` has duplicate `customer_id` rows, the JOIN produces duplicate order rows. Use `IN` or `EXISTS` when deduplication is required, or add `DISTINCT` to the JOIN.
- **Generating >100 bind parameters in one statement** — D1 enforces a 100-variable limit. Batch large lists with `db.batch()`.

---

## Gotchas

- SQLite's query planner can flatten simple `IN (SELECT …)` into a semi-join automatically (visible in `EXPLAIN QUERY PLAN` as "SEARCH … USING INDEX"). When the planner does this, `IN` and `EXISTS` perform identically. Verify with EXPLAIN rather than assuming.
- `EXPLAIN QUERY PLAN` output format changed significantly in SQLite 3.36. D1 runs a recent SQLite version; the output uses indented tree notation rather than flat rows.
- D1 does not expose `EXPLAIN` (non-QUERY-PLAN) opcode output. Use only `EXPLAIN QUERY PLAN` for query analysis.
- Binding arrays directly is not supported in the D1 JS API. Always expand arrays into individual `?` placeholders.
- For `IN` lists beyond a few hundred values, a temporary shadow table populated via `db.batch()` inserts is more efficient than a single giant `IN (?, ?, …, ?)`.

---

## Verification

```typescript
// Compare plan for IN vs EXISTS
async function compareQueryPlans(db: D1Database): Promise<void> {
  const inPlan = await explainQuery(
    db,
    `SELECT * FROM orders WHERE customer_id IN (SELECT customer_id FROM vip_customers)`
  );
  const existsPlan = await explainQuery(
    db,
    `SELECT * FROM orders o WHERE EXISTS (SELECT 1 FROM vip_customers v WHERE v.customer_id = o.customer_id)`
  );

  console.log('IN plan:', inPlan);
  console.log('EXISTS plan:', existsPlan);
  // If both show "SEARCH … USING INDEX", they are equivalent.
  // If IN shows "SCAN", add an index or rewrite as EXISTS / JOIN.
}
```

---

## Related

- `d1-sqlite-query-optimization.md`
- `composite-index-design.md`
- `covering-indexes.md`
- `cte-common-table-expressions.md`
- `subquery-vs-join.md`

---

## Sources

- https://www.sqlite.org/optoverview.html#subquery_flattening
- https://www.sqlite.org/lang_expr.html#in_op
- https://www.sqlite.org/nulls.html
- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/eqp.html
