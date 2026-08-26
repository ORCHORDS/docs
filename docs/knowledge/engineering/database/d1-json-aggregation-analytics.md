# D1 JSON Aggregation Functions for Inline Analytics

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need per-request analytics rollups — counts, sums, and grouped breakdowns — returned as structured JSON from a single D1 query inside a Cloudflare Worker. Issuing multiple round-trip queries for each metric is too slow given D1's per-query latency, and a separate OLAP store is not justified at this scale.

## Context

SQLite (and therefore D1) supports `json_group_array()` and `json_group_object()` aggregate functions since SQLite 3.38. Combined with `json_object()`, `json_each()`, and window functions, these let you collapse GROUP BY results into nested JSON structures in a single query — eliminating N+1 query patterns for dashboard endpoints. D1 returns the JSON as a plain string column; parse it in the Worker with `JSON.parse()`. All aggregation runs server-side in the SQLite engine, keeping the response payload small.

## Building a Multi-Metric Dashboard Query

```typescript
// src/analytics.ts
import type { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

interface DashboardMetrics {
  revenue_by_day: Array<{ date: string; total_cents: number; order_count: number }>;
  top_products: Array<{ product_id: number; name: string; units_sold: number }>;
  status_breakdown: Record<string, number>;
}

export async function getDashboardMetrics(
  env: Env,
  startDate: string,   // ISO 8601 e.g. '2026-07-01'
  endDate: string
): Promise<DashboardMetrics> {
  const row = await env.DB.prepare(
    `WITH filtered_orders AS (
       SELECT
         o.id,
         o.status,
         o.created_at,
         date(o.created_at) AS order_date,
         o.total_cents
       FROM orders o
       WHERE o.created_at >= ? AND o.created_at < ?
     ),
     revenue_series AS (
       SELECT
         order_date,
         SUM(total_cents)  AS total_cents,
         COUNT(*)          AS order_count
       FROM filtered_orders
       GROUP BY order_date
     ),
     product_sales AS (
       SELECT
         oi.product_id,
         p.name,
         SUM(oi.quantity) AS units_sold
       FROM order_items oi
       JOIN products p ON p.id = oi.product_id
       JOIN filtered_orders fo ON fo.id = oi.order_id
       GROUP BY oi.product_id, p.name
       ORDER BY units_sold DESC
       LIMIT 5
     ),
     status_counts AS (
       SELECT status, COUNT(*) AS cnt
       FROM filtered_orders
       GROUP BY status
     )
     SELECT
       (SELECT json_group_array(
                 json_object(
                   'date',        order_date,
                   'total_cents', total_cents,
                   'order_count', order_count
                 )
               )
        FROM revenue_series
        ORDER BY order_date)                       AS revenue_by_day,

       (SELECT json_group_array(
                 json_object(
                   'product_id', product_id,
                   'name',       name,
                   'units_sold', units_sold
                 )
               )
        FROM product_sales)                        AS top_products,

       (SELECT json_group_object(status, cnt)
        FROM status_counts)                        AS status_breakdown`
  )
    .bind(startDate, endDate)
    .first<{
      revenue_by_day: string;
      top_products: string;
      status_breakdown: string;
    }>();

  if (!row) {
    return { revenue_by_day: [], top_products: [], status_breakdown: {} };
  }

  return {
    revenue_by_day: JSON.parse(row.revenue_by_day ?? '[]'),
    top_products:   JSON.parse(row.top_products   ?? '[]'),
    status_breakdown: JSON.parse(row.status_breakdown ?? '{}'),
  };
}
```

## Expanding JSON Arrays Back into Rows with json_each

```typescript
// src/cohort.ts
// Use json_each() to pass a JSON array of IDs as a single bind parameter,
// avoiding a variable-length IN (?, ?, ...) clause.

export async function getOrdersForUsers(
  env: Env,
  userIds: number[]
): Promise<Array<{ user_id: number; order_id: number; total_cents: number }>> {
  if (userIds.length === 0) return [];

  const { results } = await env.DB.prepare(
    `SELECT
       o.user_id,
       o.id      AS order_id,
       o.total_cents
     FROM orders o
     JOIN json_each(?1) j ON j.value = o.user_id   -- expand JSON array
     ORDER BY o.created_at DESC`
  )
    .bind(JSON.stringify(userIds))
    .all<{ user_id: number; order_id: number; total_cents: number }>();

  return results;
}

// Aggregate per-user totals from the expanded set
export async function getUserSpendTotals(
  env: Env,
  userIds: number[]
): Promise<Array<{ user_id: number; lifetime_cents: number; order_count: number }>> {
  if (userIds.length === 0) return [];

  const { results } = await env.DB.prepare(
    `SELECT
       o.user_id,
       SUM(o.total_cents) AS lifetime_cents,
       COUNT(*)           AS order_count
     FROM orders o
     JOIN json_each(?1) j ON j.value = o.user_id
     GROUP BY o.user_id`
  )
    .bind(JSON.stringify(userIds))
    .all<{ user_id: number; lifetime_cents: number; order_count: number }>();

  return results;
}
```

## Nesting Aggregates for API Responses

```typescript
// src/user-summary.ts
// Return one row per user with an embedded JSON array of recent orders —
// avoids a separate query per user.

interface UserSummary {
  user_id: number;
  email: string;
  recent_orders: Array<{ id: number; created_at: string; total_cents: number }>;
}

export async function getUserSummaries(
  env: Env,
  page = 0,
  pageSize = 25
): Promise<UserSummary[]> {
  const { results } = await env.DB.prepare(
    `SELECT
       u.id   AS user_id,
       u.email,
       COALESCE(
         (SELECT json_group_array(
                   json_object(
                     'id',          o.id,
                     'created_at',  o.created_at,
                     'total_cents', o.total_cents
                   )
                 )
          FROM (
            SELECT id, created_at, total_cents
            FROM orders
            WHERE user_id = u.id
            ORDER BY created_at DESC
            LIMIT 5
          ) o),
         '[]'
       ) AS recent_orders
     FROM users u
     ORDER BY u.id
     LIMIT ?1 OFFSET ?2`
  )
    .bind(pageSize, page * pageSize)
    .all<{ user_id: number; email: string; recent_orders: string }>();

  return results.map(r => ({
    user_id: r.user_id,
    email: r.email,
    recent_orders: JSON.parse(r.recent_orders),
  }));
}
```

## Anti-patterns

- Fetching all rows into the Worker and reducing in JavaScript — wastes D1 result bandwidth and Worker CPU; aggregation belongs in SQL.
- Building `IN (${ids.join(',')})` with dynamic interpolation — creates SQL injection risk and breaks prepared statement caching; use `json_each()` with a single bound parameter instead.
- Parsing `json_group_array` results without a null guard (`?? '[]'`) — an empty GROUP returns NULL, not `'[]'`, causing `JSON.parse(null)` to throw.

## Gotchas

- `json_group_array()` with an `ORDER BY` inside is not supported in SQLite — sort via a subquery or CTE, then aggregate the pre-sorted rows.
- D1 returns integer columns accurately but JSON numbers in SQLite strings are always doubles; large `BIGINT`-equivalent values can lose precision after `JSON.parse()`. Cast to `TEXT` inside `json_object()` for 64-bit IDs.
- `json_group_object()` requires the first argument to be a text expression — `json_group_object(CAST(id AS TEXT), value)` if the key is an integer.

## Verification

```bash
# Run the dashboard query locally against a dev D1 binding
wrangler d1 execute MY_DB --local \
  --command "SELECT json_group_array(json_object('id', id, 'status', status)) FROM orders LIMIT 3;"

# Confirm json_each expansion works
wrangler d1 execute MY_DB --remote \
  --command "SELECT value FROM json_each('[1,2,3]');"

# Profile with EXPLAIN QUERY PLAN
wrangler d1 execute MY_DB --remote \
  --command "EXPLAIN QUERY PLAN SELECT SUM(total_cents) FROM orders WHERE created_at >= '2026-01-01';"
```

## Related

- `database/d1-json-column-patterns.md`
- `database/d1-json-columns-partial-indexes.md`
- `database/d1-window-functions-analytics.md`
- `database/d1-time-series-partitioning.md`
- `database/sqlite-recursive-cte-graph-queries.md`

## Sources

- https://www.sqlite.org/json1.html
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://www.sqlite.org/windowfunctions.html
