# D1 Query Observability via Cloudflare Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
D1 query latency or error rates are degrading in production but there is no structured
telemetry to pinpoint which query, which tenant, or which time window is responsible.

## Context
Cloudflare Analytics Engine (AE) is a columnar time-series store designed for high-cardinality
event data at Worker-native write throughput. Writing to AE costs nothing extra beyond the
bound-in dataset and is done via `env.AE.writeDataPoint()` — a fire-and-forget call with no
added latency to the critical path. Emitting one data point per D1 query (duration, row count,
query type, tenant ID, error flag) gives a continuous observability feed that can be queried
via the AE SQL API, Grafana, or Cloudflare's own dashboards. Unlike `console.log` or tail
workers, AE data is queryable for up to 31 days with GROUP BY, percentiles, and time-bucket
aggregations.

## Dataset Schema (Logical)

```
Dataset name: d1_query_metrics

Blob fields (dimensions — up to 20):
  blob1  = worker_name
  blob2  = query_name      -- human-readable label passed by caller
  blob3  = query_type      -- SELECT | INSERT | UPDATE | DELETE | OTHER
  blob4  = tenant_id
  blob5  = error_code      -- empty string on success

Double fields (measures — up to 20):
  double1 = duration_ms
  double2 = rows_read
  double3 = rows_written
  double4 = is_error       -- 0 or 1

Index:  timestamp (implicit, written by AE)
```

## Instrumented D1 Wrapper

```typescript
// src/db-observed.ts
export interface Env {
  DB: D1Database;
  AE: AnalyticsEngineDataset;
}

interface QueryMeta {
  name:     string;   // e.g. "get-product-by-id"
  tenantId: string;
}

function classifyQuery(sql: string): string {
  const first = sql.trimStart().substring(0, 6).toUpperCase();
  if (first.startsWith('SELECT')) return 'SELECT';
  if (first.startsWith('INSERT')) return 'INSERT';
  if (first.startsWith('UPDATE')) return 'UPDATE';
  if (first.startsWith('DELETE')) return 'DELETE';
  return 'OTHER';
}

export async function observedFirst<T>(
  env: Env,
  stmt: D1PreparedStatement,
  meta: QueryMeta & { sql: string }
): Promise<T | null> {
  const t0 = Date.now();
  let isError = 0;
  let errorCode = '';
  let result: T | null = null;

  try {
    result = await stmt.first<T>();
  } catch (err: unknown) {
    isError = 1;
    errorCode = err instanceof Error ? err.message.substring(0, 64) : 'UNKNOWN';
    throw err;
  } finally {
    const durationMs = Date.now() - t0;
    env.AE.writeDataPoint({
      blobs:   [
        'api-worker',          // blob1: worker_name
        meta.name,             // blob2: query_name
        classifyQuery(meta.sql), // blob3: query_type
        meta.tenantId,         // blob4: tenant_id
        errorCode,             // blob5: error_code
      ],
      doubles: [
        durationMs,  // double1
        0,           // double2: rows_read (not available from .first())
        0,           // double3: rows_written
        isError,     // double4
      ],
    });
  }

  return result;
}

export async function observedRun(
  env: Env,
  stmt: D1PreparedStatement,
  meta: QueryMeta & { sql: string }
): Promise<D1Result> {
  const t0 = Date.now();
  let isError = 0;
  let errorCode = '';
  let result!: D1Result;

  try {
    result = await stmt.run();
  } catch (err: unknown) {
    isError = 1;
    errorCode = err instanceof Error ? err.message.substring(0, 64) : 'UNKNOWN';
    throw err;
  } finally {
    const durationMs = Date.now() - t0;
    env.AE.writeDataPoint({
      blobs:   ['api-worker', meta.name, classifyQuery(meta.sql), meta.tenantId, errorCode],
      doubles: [durationMs, result?.meta?.rows_read ?? 0, result?.meta?.rows_written ?? 0, isError],
    });
  }

  return result;
}
```

## Usage in a Worker Route

```typescript
// src/index.ts
import { observedFirst, observedRun } from './db-observed';

export interface Env {
  DB: D1Database;
  AE: AnalyticsEngineDataset;
}

interface Product { id: string; name: string; price: number }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const tenantId = request.headers.get('X-Tenant-Id') ?? 'unknown';

    const getMatch = url.pathname.match(/^\/products\/([^/]+)$/);
    if (getMatch && request.method === 'GET') {
      const id = getMatch[1];
      const sql = 'SELECT id, name, price FROM products WHERE id = ?1 AND tenant_id = ?2';

      const row = await observedFirst<Product>(
        env,
        env.DB.prepare(sql).bind(id, tenantId),
        { name: 'get-product-by-id', tenantId, sql }
      );

      if (!row) return new Response('Not found', { status: 404 });
      return Response.json(row);
    }

    if (url.pathname === '/products' && request.method === 'POST') {
      const body = await request.json<{ name: string; price: number }>();
      const sql = 'INSERT INTO products (tenant_id, name, price) VALUES (?1, ?2, ?3)';

      await observedRun(
        env,
        env.DB.prepare(sql).bind(tenantId, body.name, body.price),
        { name: 'create-product', tenantId, sql }
      );

      return new Response(null, { status: 201 });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## wrangler.toml Binding

```toml
# wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding       = "DB"
database_name = "prod-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "d1_query_metrics"
```

## Analytics Engine SQL Queries

```sql
-- P99 query latency per query_name over the last 24 hours
SELECT
  blob2                                              AS query_name,
  quantileWeighted(0.99)(double1, 1)                AS p99_ms,
  avg(double1)                                       AS avg_ms,
  sum(double4)                                       AS error_count,
  count()                                            AS total
FROM d1_query_metrics
WHERE timestamp >= NOW() - INTERVAL '24' HOUR
GROUP BY query_name
ORDER BY p99_ms DESC
LIMIT 20;

-- Error rate by tenant over the last hour
SELECT
  blob4                                              AS tenant_id,
  100.0 * sum(double4) / count()                    AS error_rate_pct,
  count()                                            AS total_queries
FROM d1_query_metrics
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY tenant_id
HAVING total_queries > 10
ORDER BY error_rate_pct DESC;

-- 5-minute latency buckets for slow-query trending
SELECT
  toStartOfInterval(timestamp, INTERVAL '5' MINUTE) AS bucket,
  avg(double1)                                        AS avg_ms
FROM d1_query_metrics
WHERE blob3 = 'SELECT'
  AND timestamp >= NOW() - INTERVAL '6' HOUR
GROUP BY bucket
ORDER BY bucket;
```

## Anti-patterns
- Blocking the response on `writeDataPoint` — it is synchronous in signature but write delivery is best-effort and very fast; wrapping in `ctx.waitUntil` is unnecessary overhead.
- Storing full SQL text in a blob field — AE blob fields are indexed dimensions; a long SQL string causes high cardinality and inflates dataset size. Use a short `name` label instead.
- Emitting one data point per row of a result set — emit one point per *query call*, not per row.
- Omitting `tenant_id` in multi-tenant apps — without it the AE data is useless for isolating per-tenant degradation.
- Using AE for security audit logs — AE is eventually consistent and has no row-level deletion; use D1's own audit table for compliance purposes.

## Gotchas
- AE datasets are created automatically on first write — no explicit creation step is needed, but the binding must exist in `wrangler.toml`.
- AE SQL is queried via `https://api.cloudflare.com/client/v4/accounts/{accountId}/analytics_engine/sql` with Bearer auth — not through wrangler.
- The AE SQL API returns at most 10 000 rows per query; use time-bounded WHERE clauses to avoid hitting the limit.
- `double1`–`double20` and `blob1`–`blob20` are positional — the schema is defined by your code, not by AE; document the mapping or use a codegen step.
- AE data is available within ~15 seconds of write, not instantly — dashboards polling at < 30 s intervals may show incomplete buckets.

## Verification

```bash
# Deploy
npx wrangler deploy

# Send a few requests
curl https://<worker>.workers.dev/products/p1 -H 'X-Tenant-Id: tenant-a'
curl -X POST https://<worker>.workers.dev/products \
     -H 'X-Tenant-Id: tenant-a' \
     -H 'Content-Type: application/json' \
     -d '{"name":"Widget","price":4.99}'

# Query AE SQL API (wait ~15 s for data)
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  --data-urlencode "query=SELECT blob2, avg(double1) AS avg_ms, count() AS n FROM d1_query_metrics WHERE timestamp >= NOW() - INTERVAL '5' MINUTE GROUP BY blob2"
```

## Related
- [d1-query-timeout-abort-workers.md](d1-query-timeout-abort-workers.md)
- [d1-analyze-query-planner-workers.md](d1-analyze-query-planner-workers.md)
- [database-observability-tracing.md](database-observability-tracing.md)
- [time-series-data-cloudflare-analytics-engine.md](time-series-data-cloudflare-analytics-engine.md)

## Sources
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/d1/observability/metrics/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
