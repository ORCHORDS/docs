# Covering Indexes in D1 to Eliminate Table Scans

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker queries a D1 table that has grown to hundreds of thousands of rows and p95 query latency starts climbing above 50 ms. `wrangler d1 execute --command` with `EXPLAIN QUERY PLAN` reveals full table scans (`SCAN items` rather than `SEARCH items USING INDEX`). Adding covering indexes — indexes that include all columns the query reads, not just the filter columns — eliminates table heap lookups and drops query time to single-digit milliseconds.

## Context

- Runtime: Cloudflare Workers
- Database: Cloudflare D1 (SQLite-compatible)
- Tools: `wrangler d1 execute`, `performance.now()` in Workers, `EXPLAIN QUERY PLAN`
- Binding name (wrangler.toml): `DB` (D1Database)

---

## Section 1 — Reading EXPLAIN QUERY PLAN Output

```bash
# Run EXPLAIN QUERY PLAN against your D1 database
wrangler d1 execute YOUR_DB_NAME \
  --command "EXPLAIN QUERY PLAN SELECT id, status, created_at FROM orders WHERE user_id = 'u-123' AND status = 'pending' ORDER BY created_at DESC LIMIT 20;"
```

Bad output (table scan):
```
id  parent  notused  detail
2   0       0        SCAN orders
```

Good output (index-only query / covering index):
```
id  parent  notused  detail
3   0       0        SEARCH orders USING COVERING INDEX idx_orders_user_status_created (user_id=? AND status=?)
```

```bash
# Check existing indexes
wrangler d1 execute YOUR_DB_NAME \
  --command ".indexes orders"

# Or via SQL
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='orders';"
```

---

## Section 2 — Composite Index Design for Covering Queries

A covering index must include every column the query **filters on**, **sorts by**, and **selects** — in that order. The standard rule: (equality columns) → (range/sort column) → (included select columns).

```bash
# Create a covering index for:
# SELECT id, status, created_at FROM orders
# WHERE user_id = ? AND status = ?
# ORDER BY created_at DESC
# LIMIT 20;

# Column order: user_id (equality), status (equality), created_at (sort), id (SELECT)
# SQLite stores row id implicitly — id in the SELECT is free if it's the PK.

wrangler d1 execute YOUR_DB_NAME --command "
  CREATE INDEX IF NOT EXISTS idx_orders_user_status_created
  ON orders (user_id, status, created_at DESC);
"

# Verify with EXPLAIN QUERY PLAN again
wrangler d1 execute YOUR_DB_NAME --command "
  EXPLAIN QUERY PLAN
  SELECT id, status, created_at
  FROM orders
  WHERE user_id = 'u-123' AND status = 'pending'
  ORDER BY created_at DESC
  LIMIT 20;
"
```

For queries that also select payload columns (forcing a heap lookup), use `INCLUDE` syntax (SQLite 3.38+, available in D1):

```bash
# Include extra columns to avoid the heap lookup:
wrangler d1 execute YOUR_DB_NAME --command "
  CREATE INDEX IF NOT EXISTS idx_orders_user_status_created_full
  ON orders (user_id, status, created_at DESC)
  INCLUDE (amount, currency);
"
```

---

## Section 3 — Workers Query Timing with performance.now()

Measure actual D1 query time per request to establish a baseline and validate index improvements.

```typescript
export interface Env {
  DB: D1Database;
}

interface Order {
  id: string;
  status: string;
  created_at: number;
  amount: number;
  currency: string;
}

interface QueryMetrics {
  results: Order[];
  count: number;
  elapsed_ms: number;
  index_used: boolean; // inferred from timing heuristic
}

async function fetchPendingOrders(
  db: D1Database,
  userId: string,
  limit = 20,
): Promise<QueryMetrics> {
  const t0 = performance.now();

  const { results, meta } = await db
    .prepare(
      `SELECT id, status, created_at, amount, currency
       FROM orders
       WHERE user_id = ?1
         AND status = 'pending'
       ORDER BY created_at DESC
       LIMIT ?2`,
    )
    .bind(userId, limit)
    .all<Order>();

  const elapsed = performance.now() - t0;

  return {
    results,
    count: results.length,
    elapsed_ms: Math.round(elapsed * 100) / 100,
    // Heuristic: index-only queries on D1 typically complete < 5 ms
    index_used: elapsed < 5,
  };
}

async function explainQuery(db: D1Database, sql: string): Promise<string[]> {
  const { results } = await db
    .prepare(`EXPLAIN QUERY PLAN ${sql}`)
    .all<{ detail: string }>();
  return results.map((r) => r.detail);
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const userId = url.searchParams.get('user_id');
    if (!userId) return new Response('Missing user_id', { status: 400 });

    // Optional: expose query plan in dev
    const debug = url.searchParams.get('debug') === '1';

    const metrics = await fetchPendingOrders(env.DB, userId);

    let queryPlan: string[] | undefined;
    if (debug) {
      queryPlan = await explainQuery(
        env.DB,
        `SELECT id, status, created_at, amount, currency
         FROM orders
         WHERE user_id = '${userId}' AND status = 'pending'
         ORDER BY created_at DESC LIMIT 20`,
      );
    }

    return Response.json({
      orders: metrics.results,
      meta: {
        count: metrics.count,
        elapsed_ms: metrics.elapsed_ms,
        index_used: metrics.index_used,
        ...(queryPlan ? { query_plan: queryPlan } : {}),
      },
    });
  },
};
```

---

## Section 4 — Index Maintenance and Migration

```typescript
// D1 migrations: src/db/migrations/0003_add_covering_indexes.sql

const MIGRATION_SQL = `
-- Drop old partial index if it exists
DROP INDEX IF EXISTS idx_orders_user_id;

-- Add covering index for pending-orders query pattern
CREATE INDEX IF NOT EXISTS idx_orders_user_status_created
ON orders (user_id, status, created_at DESC)
INCLUDE (amount, currency);

-- Add covering index for admin all-orders-by-date query
CREATE INDEX IF NOT EXISTS idx_orders_created_status
ON orders (created_at DESC, status)
INCLUDE (user_id, amount);

-- Rebuild statistics so the query planner picks the right index
ANALYZE orders;
`;

// Apply via wrangler:
// wrangler d1 migrations apply YOUR_DB_NAME

// Or programmatically in a Worker one-shot endpoint (admin use only):
async function applyMigration(db: D1Database): Promise<void> {
  const statements = MIGRATION_SQL
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => db.prepare(s));

  await db.batch(statements);
}
```

---

## Anti-patterns

- Creating an index on the filter column only (e.g., `CREATE INDEX ON orders (user_id)`) — the query planner still does a heap lookup for every matched row to fetch `status`, `created_at`, `amount`
- Putting the sort column before equality columns — `(created_at, user_id, status)` cannot satisfy `WHERE user_id = ? AND status = ?` efficiently
- Over-indexing: creating one index per query pattern — each index adds write overhead; consolidate patterns that share a common prefix
- Using `SELECT *` in production queries — fetches all columns, defeating covering indexes that don't `INCLUDE` every column
- Skipping `ANALYZE` after bulk inserts — the query planner uses stale row-count statistics and may choose a sub-optimal plan

## Gotchas

- D1 is SQLite-compatible but not identical — some SQLite extensions (FTS5 full text, R-Tree) are available but check the D1 changelog before relying on them
- `INCLUDE` columns in an index require SQLite 3.38.0+; D1 as of 2024 supports this, but older `wrangler d1 local` SQLite versions may not
- D1 indexes are eventually consistent across read replicas — an index created on the primary is available on replicas within seconds, not instantly
- `performance.now()` in Workers measures wall-clock time including network round-trip to D1; isolate-local operations are sub-millisecond
- Covering indexes increase storage usage; monitor with `wrangler d1 info YOUR_DB_NAME` for size

## Verification

```bash
DB="YOUR_DB_NAME"

# 1. Check current index list
wrangler d1 execute $DB \
  --command "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='orders';"

# 2. Explain key queries BEFORE and AFTER index creation
wrangler d1 execute $DB \
  --command "EXPLAIN QUERY PLAN SELECT id, status, created_at, amount FROM orders WHERE user_id='u-123' AND status='pending' ORDER BY created_at DESC LIMIT 20;"

# 3. Run ANALYZE to update statistics
wrangler d1 execute $DB --command "ANALYZE orders;"

# 4. Deploy Worker and measure p50/p95 via tail
wrangler deploy
wrangler tail --format pretty

# 5. Load test to capture percentiles
npx autocannon -c 50 -d 10 \
  'https://your-worker.workers.dev/?user_id=u-123'
```

## Related

- `documentation/categories/performance/workers-cache-ttl-tiered-kv-strategy.md`
- `documentation/categories/performance/workers-wasm-compute-offload-performance.md`

## Sources

- https://developers.cloudflare.com/d1/build-databases/query-databases/
- https://developers.cloudflare.com/d1/reference/sql-api/
- https://www.sqlite.org/queryplanner.html
- https://www.sqlite.org/lang_createindex.html
- https://developers.cloudflare.com/d1/best-practices/
