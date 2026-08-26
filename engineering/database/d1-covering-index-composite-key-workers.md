# D1 Covering Index and Composite Key Performance in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Queries against a Cloudflare D1 table are reading many rows or triggering full table scans even though an index exists on the filter column. Adding more columns to the SELECT list makes performance worse. You need sub-millisecond latency on hot read paths inside a Worker and want to avoid unnecessary row lookups.

## Context

SQLite (and therefore D1) uses a B-tree index structure. A **covering index** is one that contains every column a query needs — the filter columns, the ORDER BY columns, and all columns in the SELECT list. When the query planner can satisfy the entire query from the index without touching the table rows, it performs an **index-only scan**, which is substantially faster. In D1 on the Cloudflare edge this matters doubly: Workers have tight CPU time budgets and each row lookup is a random I/O into the table page. Composite key order and included-column order both determine whether the planner picks the covering path.

---

## 1. How SQLite Chooses a Covering Index

SQLite's query planner (NGQP) marks a search as "covering" when the index B-tree node already holds every column the query references. Use `EXPLAIN QUERY PLAN` to confirm — look for `USING COVERING INDEX` rather than plain `USING INDEX`.

```typescript
// workers/src/db/explain.ts
export async function explainQuery(db: D1Database, sql: string, bindings: unknown[]) {
  const rows = await db
    .prepare(`EXPLAIN QUERY PLAN ${sql}`)
    .bind(...bindings)
    .all<{ id: number; parent: number; notused: number; detail: string }>();

  const isCovering = rows.results.some(r => r.detail.includes('COVERING INDEX'));
  console.log({ isCovering, plan: rows.results.map(r => r.detail) });
  return rows.results;
}
```

---

## 2. Building a Composite Covering Index

Column order in the index must follow the **equality → range → include** rule: put equality-filter columns first, range-filter or ORDER BY columns next, then remaining SELECT columns at the end.

```sql
-- Schema: orders table with tenant isolation
CREATE TABLE orders (
  id        TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  status    TEXT NOT NULL,        -- equality filter
  created_at INTEGER NOT NULL,    -- range / ORDER BY
  total_cents INTEGER NOT NULL,   -- included for SELECT
  user_id   TEXT NOT NULL         -- included for SELECT
);

-- Covering index: tenant_id + status (equality) → created_at (range/order) → total_cents, user_id (include)
CREATE INDEX idx_orders_covering
  ON orders (tenant_id, status, created_at, total_cents, user_id);
```

```typescript
// workers/src/handlers/orders.ts
export async function getRecentOrders(
  db: D1Database,
  tenantId: string,
  status: string,
  afterTs: number,
  limit = 20
): Promise<Order[]> {
  const { results } = await db
    .prepare(
      `SELECT id, created_at, total_cents, user_id
       FROM orders
       WHERE tenant_id = ? AND status = ? AND created_at > ?
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .bind(tenantId, status, afterTs, limit)
    .all<Order>();
  return results;
}
```

The query touches only the index B-tree — no table row reads.

---

## 3. Composite Primary Keys and Index Interaction

In SQLite every secondary index implicitly appends the rowid (or PRIMARY KEY columns for WITHOUT ROWID tables). If your primary key is wide (e.g., a composite `(tenant_id, id)`), every secondary index carries those columns for free. This means you can sometimes shorten the explicit covering index.

```sql
-- WITHOUT ROWID table with composite PK
CREATE TABLE sessions (
  tenant_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, session_id)
) WITHOUT ROWID;

-- Secondary index only needs expires_at; tenant_id+session_id are implicit
CREATE INDEX idx_sessions_expiry
  ON sessions (tenant_id, expires_at);

-- This query is covered: tenant_id + expires_at from the index,
-- session_id from the implicit PK suffix
SELECT session_id FROM sessions
WHERE tenant_id = ? AND expires_at < ?;
```

---

## 4. Partial Covering Indexes for Hot Subsets

Combine a covering index with a WHERE clause to shrink index size and improve cache efficiency for the most queried rows.

```sql
-- Only index active orders — covers 5% of rows but 90% of queries
CREATE INDEX idx_orders_active_covering
  ON orders (tenant_id, created_at DESC, total_cents, user_id)
  WHERE status = 'active';
```

```typescript
// Must include the predicate in the query for the planner to pick it
export async function getActiveOrders(db: D1Database, tenantId: string) {
  const { results } = await db
    .prepare(
      `SELECT id, created_at, total_cents, user_id
       FROM orders
       WHERE tenant_id = ? AND status = 'active'
       ORDER BY created_at DESC
       LIMIT 50`
    )
    .bind(tenantId)
    .all<Order>();
  return results;
}
```

---

## 5. Verifying Index Usage in a Migration

Embed an `EXPLAIN QUERY PLAN` assertion in the migration so CI catches regressions before they reach production.

```typescript
// migrations/verify-indexes.ts
import type { D1Database } from '@cloudflare/workers-types';

interface PlanRow { detail: string }

export async function verifyOrderIndexCovering(db: D1Database): Promise<void> {
  const sql = `SELECT id, created_at, total_cents, user_id
               FROM orders
               WHERE tenant_id = 'x' AND status = 'active' AND created_at > 0
               ORDER BY created_at DESC LIMIT 10`;

  const { results } = await db
    .prepare(`EXPLAIN QUERY PLAN ${sql}`)
    .all<PlanRow>();

  const covered = results.some(r => r.detail.toUpperCase().includes('COVERING INDEX'));
  if (!covered) {
    throw new Error(`Index regression: query no longer uses a covering index.\nPlan:\n${results.map(r => r.detail).join('\n')}`);
  }
}
```

---

## 6. Index-Only Aggregations

Covering indexes accelerate COUNT, SUM, and MAX when all referenced columns are indexed.

```sql
-- This index covers the aggregation below
CREATE INDEX idx_orders_tenant_status_total
  ON orders (tenant_id, status, total_cents);
```

```typescript
export async function getOrderStats(
  db: D1Database,
  tenantId: string
): Promise<{ status: string; count: number; total: number }[]> {
  const { results } = await db
    .prepare(
      `SELECT status, COUNT(*) AS count, SUM(total_cents) AS total
       FROM orders
       WHERE tenant_id = ?
       GROUP BY status`
    )
    .bind(tenantId)
    .all<{ status: string; count: number; total: number }>();
  return results;
}
```

---

## Anti-patterns

- **Select star defeats covering indexes.** `SELECT *` always forces a table lookup. Select only needed columns.
- **Wrong column order.** Putting ORDER BY columns before equality columns prevents efficient range pruning and covering.
- **Over-indexing.** One covering index per query pattern bloats the database. Consolidate: a 5-column covering index can serve multiple query shapes by serving prefix subsets.
- **Ignoring implicit PK suffix.** In WITHOUT ROWID tables the PK is already appended; duplicating it wastes space.
- **Covering indexes on TEXT blobs.** Storing large text in an index column defeats the space efficiency; store a hash or a short key column instead.

---

## Gotchas

- SQLite rewrites `NOT IN` and `!=` predicates in ways that prevent index use; use `> ?` or a join instead.
- `LIKE '%foo%'` leading wildcards bypass all indexes including covering ones.
- D1 runs SQLite 3.x; partial index support requires `status = 'active'` (literal), not a bind parameter, in the index WHERE clause.
- After adding a covering index via a D1 migration, existing prepared statements in the Worker are re-planned on first use — no cache flush is needed.
- The planner may choose a table scan over a covering index if SQLite's statistics are stale; run `ANALYZE` after large data loads.

---

## Verification

```sql
-- Confirm covering index is selected
EXPLAIN QUERY PLAN
SELECT id, created_at, total_cents, user_id
FROM orders
WHERE tenant_id = 'demo' AND status = 'active' AND created_at > 1700000000
ORDER BY created_at DESC
LIMIT 20;
-- Expected output contains: USING COVERING INDEX idx_orders_active_covering

-- Check index size vs table size
SELECT name, tbl_name
FROM sqlite_master
WHERE type = 'index' AND tbl_name = 'orders';
```

---

## Related

- `d1-sqlite-query-optimization.md`
- `composite-index-design.md`
- `covering-indexes.md`
- `d1-partial-index-filtered-workers.md`
- `d1-without-rowid-table-design.md`
- `d1-analyze-query-planner-workers.md`

---

## Sources

- https://www.sqlite.org/queryplanner.html
- https://www.sqlite.org/optoverview.html#covering_indices
- https://developers.cloudflare.com/d1/reference/database-commands/
- https://www.sqlite.org/partialindex.html
