# D1 Covering Index Multi-Column Query Optimization

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A D1 query that filters on an indexed column is still slow. `EXPLAIN QUERY PLAN`
shows the index being used (`SEARCH orders USING INDEX idx_orders_user_id`) but
response times remain higher than expected. The problem is an invisible secondary
step: after locating matching index entries, SQLite fetches each matching row from
the main table (B-tree) to retrieve columns not present in the index. This is called
a **table lookup** or **rowid lookup**, and it doubles the I/O compared to a query
that can be satisfied entirely from the index.

A **covering index** includes every column the query needs — filters, sort keys, and
projected columns — so SQLite never touches the main table. D1's underlying SQLite
engine fully supports multi-column covering indexes.

## Context

SQLite indexes are B-trees sorted by the indexed column(s). A query against an index
typically:
1. Traverses the index B-tree to find rows matching the `WHERE` clause.
2. For each match, follows the rowid pointer to fetch the full row from the main table.

Step 2 is random I/O. On a large table it can cost as much as the index scan itself.

A covering index eliminates step 2 by storing additional columns alongside the index
key. When SQLite recognizes that all columns referenced in a query (`WHERE`, `ORDER
BY`, `SELECT`) are present in the index, it marks the query plan as
`USING INDEX ... (COVERING)` and skips the table lookup entirely.

D1 runs SQLite in WAL mode inside Cloudflare's distributed storage layer. Each
avoided rowid lookup reduces round-trips into the storage engine, which compounds
in D1 where latency per I/O operation is higher than local disk SQLite.

## Anatomy of a Covering Index

```sql
-- Table schema
CREATE TABLE orders (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  status      TEXT NOT NULL,        -- 'pending' | 'shipped' | 'delivered'
  created_at  INTEGER NOT NULL,     -- Unix timestamp ms
  total_cents INTEGER NOT NULL,
  notes       TEXT
);

-- Target query: list a user's pending orders, newest first, show id + total.
SELECT id, total_cents
FROM orders
WHERE user_id = ?
  AND status  = 'pending'
ORDER BY created_at DESC
LIMIT 20;
```

```sql
-- Non-covering index: filters correctly but triggers rowid lookups for
-- id, total_cents, created_at (not in index).
CREATE INDEX idx_orders_user_status
  ON orders (user_id, status);

-- EXPLAIN QUERY PLAN output:
-- SEARCH orders USING INDEX idx_orders_user_status (user_id=? AND status=?)
-- (no COVERING keyword — table lookup happens for every matched row)
```

```sql
-- Covering index: includes all columns the query touches.
-- Column order: equality filters first, then sort key, then projected columns.
CREATE INDEX idx_orders_covering
  ON orders (user_id, status, created_at DESC, id, total_cents);

-- EXPLAIN QUERY PLAN output:
-- SEARCH orders USING COVERING INDEX idx_orders_covering
--   (user_id=? AND status=? AND created_at<?)
-- No table lookup — all required data is in the index.
```

## Column Ordering Rules

The column order inside a covering index determines which predicates the B-tree can
use for range narrowing. Follow this sequence:

1. **Equality columns first** — columns that appear in `WHERE col = ?`. SQLite can
   use them to jump directly to the matching subtree.
2. **Range / sort column next** — the column used in `ORDER BY` or a range predicate
   (`BETWEEN`, `>`, `<`). Only one range column can leverage the B-tree ordering.
3. **Remaining projected columns last** — columns needed only in the `SELECT` list.
   Their order among themselves does not affect query plan quality; they are carried
   along for free.

```sql
-- Good: equality (user_id, status) → sort (created_at) → projected (id, total_cents)
CREATE INDEX idx_orders_covering
  ON orders (user_id, status, created_at DESC, id, total_cents);

-- Bad: projected columns interspersed before the sort key.
-- SQLite cannot use the B-tree order for created_at after a non-equality column.
CREATE INDEX idx_orders_bad
  ON orders (user_id, id, status, total_cents, created_at);
```

## Workers Implementation

```typescript
// worker/orders.ts
import type { D1Database } from "@cloudflare/workers-types";

interface Order {
  id: string;
  total_cents: number;
}

const GET_PENDING_ORDERS = `
  SELECT id, total_cents
  FROM   orders
  WHERE  user_id = ?
    AND  status  = 'pending'
  ORDER BY created_at DESC
  LIMIT 20
`;

// Prepared statement cached in module scope — compiled once per isolate.
let pendingOrdersStmt: ReturnType<D1Database["prepare"]> | null = null;

export async function getPendingOrders(
  db: D1Database,
  userId: string
): Promise<Order[]> {
  if (pendingOrdersStmt === null) {
    pendingOrdersStmt = db.prepare(GET_PENDING_ORDERS);
  }
  const result = await pendingOrdersStmt.bind(userId).all<Order>();
  return result.results;
}
```

```typescript
// worker/migrate.ts — run once during schema migration.
export async function createCoveringIndex(db: D1Database): Promise<void> {
  await db.exec(`
    CREATE INDEX IF NOT EXISTS idx_orders_covering
      ON orders (user_id, status, created_at DESC, id, total_cents)
  `);
  // Rebuild statistics so the planner knows about the new index.
  await db.prepare("PRAGMA optimize=0x10002").run();
}
```

## Verifying a Covering Index is Used

```typescript
// worker/diagnose.ts
export async function checkQueryPlan(db: D1Database, userId: string): Promise<void> {
  const plan = await db
    .prepare(`
      EXPLAIN QUERY PLAN
      SELECT id, total_cents
      FROM   orders
      WHERE  user_id = ? AND status = 'pending'
      ORDER BY created_at DESC
      LIMIT 20
    `)
    .bind(userId)
    .all();

  const planText = plan.results.map((r: Record<string, unknown>) => r.detail).join("\n");
  const isCovering = planText.includes("COVERING");

  console.log("Plan:", planText);
  console.log("Covering index active:", isCovering);
  // Should print: "Covering index active: true"
}
```

## Trade-offs and Index Maintenance Cost

A covering index stores more data per entry (additional columns alongside the key).
This increases index size and slows `INSERT`/`UPDATE`/`DELETE` operations slightly
because more index entries must be written and maintained.

| Factor               | Non-covering index | Covering index             |
|----------------------|--------------------|----------------------------|
| Read performance     | Index scan + table lookup | Index scan only       |
| Write overhead       | Lower (smaller entries) | Higher (more data per entry) |
| Index storage size   | Smaller            | Larger                     |
| Suitable for         | High write / low read | High read / selective query |

Apply covering indexes selectively to your highest-frequency read queries. Not every
query needs a covering index; start with the queries that `EXPLAIN QUERY PLAN` shows
as doing table lookups with large intermediate result sets.

## Partial Covering Index (Filtered Index)

When a query always filters on a specific value (e.g., `status = 'pending'`), a
partial index reduces index size by excluding rows that never match:

```sql
-- Only index pending orders — a fraction of total rows on a busy table.
CREATE INDEX idx_pending_orders_covering
  ON orders (user_id, created_at DESC, id, total_cents)
  WHERE status = 'pending';
```

SQLite uses this index only when the query includes `AND status = 'pending'` literally
(not as a bound parameter for `status = ?`). This restriction limits its applicability
but makes the index significantly smaller and faster to scan.

## Anti-patterns

- **Including every column**: Adding all table columns to an index as a blanket rule
  makes writes slower than necessary and wastes storage. Include only columns the
  query actually projects.
- **Relying on covering indexes as a substitute for query optimization**: A covering
  index on a query that returns 100,000 rows still materializes 100,000 rows. Add a
  `LIMIT` and ensure the query is selective.
- **Creating covering indexes on high-write tables without benchmarking**: Measure
  write throughput before and after adding a covering index on a table with
  >10,000 writes/hour.
- **Ordering equality columns after range columns**: Placing a range-predicate column
  before equality columns prevents SQLite from narrowing the index scan efficiently,
  undermining the covering index benefit.

## Gotchas

- **`DESC` in the index key**: SQLite 3.37+ (which D1 uses) supports `DESC` on
  individual index columns. Matching the `ORDER BY ... DESC` direction in the index
  avoids a sort step. Confirm with `EXPLAIN QUERY PLAN` — look for the absence of
  `USE TEMP B-TREE FOR ORDER BY`.
- **`TEXT` vs. `INTEGER` sort order**: SQLite sorts `TEXT` lexicographically and
  `INTEGER` numerically. Storing timestamps as `INTEGER` (Unix ms) instead of
  `TEXT` (ISO string) produces correct chronological index order.
- **Column affinity in the index**: SQLite index entries store values with the same
  affinity as the column declaration. Mismatched types in `bind()` calls (e.g.,
  passing a number where the column is `TEXT`) will miss the index.
- **`PRAGMA optimize` after index creation**: A freshly created index has no entry
  in `sqlite_stat1`. Run `PRAGMA optimize=0x10002` after creating a covering index
  to ensure the query planner has accurate selectivity data.

## Verification

Measure before and after:

```typescript
async function benchmark(db: D1Database, userId: string, label: string): Promise<void> {
  const start = Date.now();
  for (let i = 0; i < 50; i++) {
    await db
      .prepare("SELECT id, total_cents FROM orders WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 20")
      .bind(userId)
      .all();
  }
  console.log(`${label}: ${Date.now() - start} ms total for 50 calls`);
}

await benchmark(env.DB, testUserId, "Before covering index");
await env.DB.exec("CREATE INDEX IF NOT EXISTS idx_orders_covering ON orders (user_id, status, created_at DESC, id, total_cents)");
await env.DB.prepare("PRAGMA optimize=0x10002").run();
await benchmark(env.DB, testUserId, "After covering index");
```

Typical results on a 100,000-row `orders` table: 40–70 % reduction in per-query
latency when the non-covering index triggered many rowid lookups.

## Related

- `d1-query-performance-explain-index.md`
- `d1-pragma-optimize-query-planner.md`
- `d1-query-optimization.md`
- `d1-prepared-statement-reuse.md`
- `index-strategy-performance.md`

## Sources

- SQLite query optimizer covering indexes: https://www.sqlite.org/queryplanner.html#covidx
- SQLite CREATE INDEX: https://www.sqlite.org/lang_createindex.html
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- SQLite partial indexes: https://www.sqlite.org/partialindex.html
