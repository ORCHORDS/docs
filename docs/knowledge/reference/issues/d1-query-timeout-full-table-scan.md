# D1 Queries Timing Out With "1000ms Exceeded" on Large Tables

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare D1 query begins failing with a `D1_ERROR: Query exceeded time limit of 1000ms` error after the table grows beyond a few hundred thousand rows. The query worked fine during development and early production but degrades as data accumulates. The timeout happens on reads, not writes, and the affected queries typically filter by a non-primary-key column.

---

## Context

D1 is SQLite running at the edge. SQLite's query planner performs a full table scan (reading every row) when no suitable index exists for the `WHERE`, `ORDER BY`, or `JOIN` condition. At small data volumes this is fast enough to be invisible; at large volumes the scan takes longer than D1's 1000ms execution limit. Unlike managed databases, D1 does not currently emit slow-query warnings before the timeout fires. The only reliable diagnostic tool is `EXPLAIN QUERY PLAN`, which shows whether the planner chose a scan or an index seek. Adding a covering index converts `O(n)` scans to `O(log n)` seeks and typically drops query time from seconds to single-digit milliseconds.

---

## Root Cause

A `WHERE` clause on an un-indexed column forces SQLite to scan every row in the table.

```typescript
// BAD: query on un-indexed column — full table scan on large tables
import type { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userId = url.searchParams.get('userId');

    // orders.user_id has no index — SQLite reads every row
    const { results } = await env.DB
      .prepare('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20')
      .bind(userId)
      .all();

    return Response.json(results);
  },
};
```

Query plan before the fix (run in the D1 console or via the API):

```sql
EXPLAIN QUERY PLAN
  SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20;
-- Output:
-- QUERY PLAN
-- `--SCAN orders          <-- full table scan: reads all N rows
```

## Fix

Create a covering index on `(user_id, created_at DESC)` so the query planner can satisfy both the `WHERE` filter and the `ORDER BY` in a single index seek without touching the table heap.

```sql
-- Migration: add covering index
CREATE INDEX IF NOT EXISTS idx_orders_user_created
  ON orders (user_id, created_at DESC);
```

```typescript
// Apply the index via a D1 migration file: migrations/0004_add_orders_user_index.sql
// Then run: npx wrangler d1 migrations apply my-database --remote

// The query itself is unchanged — SQLite picks up the new index automatically
import type { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userId = url.searchParams.get('userId');

    if (!userId) {
      return new Response('Missing userId', { status: 400 });
    }

    const { results } = await env.DB
      .prepare('SELECT id, amount, status, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20')
      .bind(userId)
      .all();

    return Response.json(results);
  },
};
```

Query plan after the fix:

```sql
EXPLAIN QUERY PLAN
  SELECT id, amount, status, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20;
-- Output:
-- QUERY PLAN
-- `--SEARCH orders USING INDEX idx_orders_user_created (user_id=?)  <-- index seek
```

## Verification

```bash
# 1. Check the current query plan on the remote database
npx wrangler d1 execute my-database --remote \
  --command "EXPLAIN QUERY PLAN SELECT * FROM orders WHERE user_id = 'test' ORDER BY created_at DESC LIMIT 20;"
# Look for SCAN (bad) vs SEARCH USING INDEX (good)

# 2. Apply the migration
npx wrangler d1 migrations apply my-database --remote

# 3. Verify the index was created
npx wrangler d1 execute my-database --remote \
  --command "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='orders';"

# 4. Re-run EXPLAIN QUERY PLAN — should now show SEARCH USING INDEX
npx wrangler d1 execute my-database --remote \
  --command "EXPLAIN QUERY PLAN SELECT id, amount, status, created_at FROM orders WHERE user_id = 'test' ORDER BY created_at DESC LIMIT 20;"

# 5. Measure wall-clock time before/after (requires a timing-aware test script)
curl -w '@-' -o /dev/null -s \
  'https://my-worker.example.workers.dev/orders?userId=abc123' <<< \
  'time_total: %{time_total}s\n'
# Before fix: ~0.95s (near the 1000ms limit)
# After fix:  ~0.012s
```

---

## Anti-patterns

- **`SELECT *` on large tables** — Fetching every column prevents covering-index optimizations and increases data transfer. Select only the columns you need.
- **No migration file for the index** — Adding an index directly in the D1 console or with a one-off `wrangler d1 execute` command means the index is missing in new environments (preview, staging) and is not version-controlled.
- **Single-column index when query sorts** — An index on `(user_id)` alone does not cover the `ORDER BY created_at DESC`, so SQLite still needs a sort step. Include all `WHERE` and `ORDER BY` columns in the index in the correct order.
- **Over-indexing** — Every index adds write overhead and storage. Only add indexes for known slow query patterns; measure before and after.

---

## Gotchas

- D1 runs SQLite 3.x. The `EXPLAIN QUERY PLAN` output format changed in SQLite 3.36 — on older builds you see a flat list with `detail` column; on newer builds you see the tree format shown above.
- `DESC` in the index definition matters for `ORDER BY ... DESC` queries. A `(user_id, created_at)` index (ascending) does not eliminate the sort for a `DESC` order without an extra step.
- D1's 1000ms limit includes network round-trips between the Worker and the D1 instance. If the Worker and D1 database are in different regions, latency alone can consume 100–200ms even for fast queries.
- Running `ANALYZE` after creating the index updates SQLite's statistics tables and helps the query planner choose the new index. D1 runs `ANALYZE` automatically on schema changes, but you can trigger it manually: `npx wrangler d1 execute my-database --remote --command "ANALYZE;"`.
- Partial indexes (`CREATE INDEX ... WHERE status = 'active'`) can dramatically reduce index size for filtered queries but are only used when the `WHERE` clause exactly matches the partial index predicate.

---

## Related

- `kv-list-pagination-missing-keys.md`
- `workers-cron-missed-execution-recovery.md`

---

## Sources

- Cloudflare D1 Query Timeouts — https://developers.cloudflare.com/d1/observability/debug-d1/
- SQLite EXPLAIN QUERY PLAN — https://www.sqlite.org/eqp.html
- SQLite Query Optimizer Overview — https://www.sqlite.org/optoverview.html
- Cloudflare D1 Migrations — https://developers.cloudflare.com/d1/reference/migrations/
