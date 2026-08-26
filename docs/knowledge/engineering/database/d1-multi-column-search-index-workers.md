# D1 Multi-Column Search Index Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1-backed search endpoint is slow or doing full-table scans for queries that filter on multiple columns simultaneously — e.g. `WHERE status = 'active' AND category_id = 3 AND created_at > ?`. Adding individual single-column indexes does not fix the problem because SQLite can only use one index per table scan unless the query planner merges them with a bitmap intersection (which it often won't for D1's read-path profile).

## Context

SQLite (and therefore D1) supports composite multi-column indexes that cover several filter columns in a single B-tree. When all filter and sort columns are present in one index, the planner performs an **index range scan** with no table row look-ups for qualifying rows, known as a **covering index** when the SELECT columns are also included. The column order within the index is critical: equality predicates must precede range predicates; the final index column is the one that permits a range scan. D1's query planner is SQLite 3.x — the same `EXPLAIN QUERY PLAN` grammar applies.

## Choosing Column Order

Use this heuristic for the index column ordering:

1. Equality filter columns with the **highest selectivity** first.
2. Additional equality filter columns.
3. The range or sort column last (it can only be ranged if all preceding columns are equality-bound).

```sql
-- Query to optimize:
-- WHERE status = ? AND category_id = ? AND created_at > ? ORDER BY created_at DESC

-- Correct index (status, category_id are equality; created_at is range+sort):
CREATE INDEX idx_products_status_cat_created
  ON products(status, category_id, created_at DESC);

-- Wrong order — range column in the middle blocks the sort from using the index:
-- CREATE INDEX idx_bad ON products(status, created_at, category_id);
```

## Creating Indexes in D1 Migrations

```typescript
// migrations/0005_multi_col_indexes.sql
export const sql = `
CREATE INDEX IF NOT EXISTS idx_orders_status_customer_created
  ON orders(status, customer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_listings_active_region_price
  ON listings(is_active, region_id, price ASC);

-- Covering index: SELECT id, title without hitting the table
CREATE INDEX IF NOT EXISTS idx_articles_cat_pub_id_title
  ON articles(category_id, published_at DESC, id, title);
`;
```

Run via Wrangler:

```bash
wrangler d1 migrations apply MY_DB --remote
```

## Verifying Index Usage with EXPLAIN QUERY PLAN

```typescript
// src/debug.ts
export async function explainQuery(
  db: D1Database,
  sql: string,
  params: (string | number | null)[]
): Promise<void> {
  const { results } = await db
    .prepare(`EXPLAIN QUERY PLAN ${sql}`)
    .bind(...params)
    .all<{ id: number; parent: number; notused: number; detail: string }>();

  for (const row of results) {
    console.log(row.detail);
    // Desired output: "SEARCH orders USING INDEX idx_orders_status_customer_created (status=? AND customer_id=? AND created_at>?)"
    // Bad output:     "SCAN orders"
  }
}
```

## Multi-Column Query with Typed Worker Handler

```typescript
// src/handlers/orders.ts
interface Env { DB: D1Database }

interface OrderRow {
  id: string;
  customer_id: string;
  status: string;
  created_at: string;
  total_cents: number;
}

export async function listOrders(
  env: Env,
  status: string,
  customerId: string,
  after: string,       // ISO timestamp cursor
  limit = 50
): Promise<OrderRow[]> {
  const { results } = await env.DB
    .prepare(`
      SELECT id, customer_id, status, created_at, total_cents
      FROM orders
      WHERE status       = ?
        AND customer_id  = ?
        AND created_at   < ?
      ORDER BY created_at DESC
      LIMIT ?
    `)
    .bind(status, customerId, after, limit)
    .all<OrderRow>();

  return results;
}
```

The query above uses `idx_orders_status_customer_created` as a single index range scan — no merge or table scan.

## Partial Covering Index for Low-Cardinality Filters

When one column is boolean or a small enum, a partial index reduces index size by omitting the dominant case:

```sql
-- Only index rows where is_active = 1 (typical: 20% of rows vs 80% inactive)
CREATE INDEX idx_listings_active_region_price
  ON listings(region_id, price ASC)
  WHERE is_active = 1;
```

```typescript
// Query — the WHERE clause must match the partial index condition exactly
const { results } = await env.DB
  .prepare(`
    SELECT id, title, price
    FROM listings
    WHERE is_active = 1
      AND region_id = ?
      AND price BETWEEN ? AND ?
    ORDER BY price ASC
    LIMIT 20
  `)
  .bind(regionId, minPrice, maxPrice)
  .all();
```

## Analyzing Index Bloat in CI

Detect runaway index creation in migration review by counting indexes per table:

```typescript
export async function auditIndexes(db: D1Database): Promise<void> {
  const { results } = await db
    .prepare(`
      SELECT tbl_name, COUNT(*) AS idx_count
      FROM sqlite_master
      WHERE type = 'index' AND sql IS NOT NULL
      GROUP BY tbl_name
      HAVING COUNT(*) > 5
    `)
    .all<{ tbl_name: string; idx_count: number }>();

  for (const { tbl_name, idx_count } of results) {
    console.warn(`Table "${tbl_name}" has ${idx_count} indexes — review for redundancy`);
  }
}
```

## Anti-patterns

- **Creating a separate index for each column**: SQLite rarely merges multiple single-column indexes efficiently. One well-ordered composite index outperforms three single-column indexes for the same multi-column query.
- **Putting the high-range column first**: `(created_at, status, category_id)` can only range-scan on `created_at`; the other columns become post-filter conditions scanned over the matching range rows.
- **Using `OR` across indexed columns**: `WHERE status = 'active' OR category_id = 3` prevents index usage. Rewrite as two queries merged with `UNION ALL` if needed.
- **Indexing every column**: write amplification increases on every `INSERT`/`UPDATE`. Index only columns present in actual `WHERE` and `ORDER BY` clauses in production queries.

## Gotchas

- `DESC` on an index column only matters when that column is the **last** range/sort column. Mismatched sort direction between index and query forces a filesort.
- D1 does not expose `ANALYZE` results persistently across requests; the planner uses built-in heuristics. If a query regresses, check that bind parameters match the column's declared affinity (TEXT vs INTEGER).
- Index names must be unique **across the entire database**, not just per table. Use a naming convention like `idx_{table}_{col1}_{col2}`.
- Partial indexes (`WHERE` clause on `CREATE INDEX`) are only used when the query's `WHERE` clause syntactically subsumes the index's filter — the literal must match exactly.

## Verification

```typescript
// Run explain and assert index is used
const plan = await env.DB
  .prepare('EXPLAIN QUERY PLAN SELECT id FROM orders WHERE status = ? AND customer_id = ? AND created_at < ?')
  .bind('pending', 'usr_123', new Date().toISOString())
  .all<{ detail: string }>();

const usesIndex = plan.results.some((r) =>
  r.detail.includes('idx_orders_status_customer_created')
);
console.assert(usesIndex, 'Query must use the composite index');
```

## Related

- `d1-covering-index-composite-key-workers.md`
- `d1-partial-index-filtered-queries-workers.md`
- `d1-analyze-query-planner-workers.md`
- `d1-pagination-cursor-keyset.md`

## Sources

- SQLite index documentation: https://www.sqlite.org/queryplanner.html
- D1 query best practices: https://developers.cloudflare.com/d1/best-practices/query-d1/
- SQLite EXPLAIN QUERY PLAN: https://www.sqlite.org/eqp.html
