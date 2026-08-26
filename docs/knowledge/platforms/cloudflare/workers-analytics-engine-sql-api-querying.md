# Cloudflare Analytics Engine SQL API — Blobs, Doubles, and Time-Series Aggregation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A team writes custom metrics to Analytics Engine from Workers but can only retrieve data
through the GraphQL API which has limited aggregation support and strict query depth rules.
Switching to the Analytics Engine SQL API unlocks `GROUP BY`, window functions, `HAVING`,
and `ORDER BY` on arbitrary time ranges — enabling dashboards that the GraphQL endpoint
cannot express.

## Context

Analytics Engine exposes two query surfaces:

| API | Endpoint | Strengths | Limits |
|---|---|---|---|
| GraphQL | `api.cloudflare.com/client/v4/graphql` | Consistent with other CF analytics | Limited aggregation, fixed intervals |
| **SQL API** | `api.cloudflare.com/client/v4/accounts/{id}/analytics_engine/sql` | Full SQL (ClickHouse dialect) | Read-only; no JOINs across datasets |

The SQL API targets the same ClickHouse-backed store. Rows are immutable append-only
events; the table name is always `$<DATASET>` (dollar-sign prefix).

---

## Writing Events from a Worker

```ts
// wrangler.toml
// [[analytics_engine_datasets]]
// binding = "AE"
// dataset = "api_events"

interface Env {
  AE: AnalyticsEngineDataset;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);

    // writeDataPoint is non-blocking fire-and-forget
    env.AE.writeDataPoint({
      // blobs: string labels (blob1–blob20)
      blobs: [
        req.method,           // blob1
        url.pathname,         // blob2
        req.headers.get('cf-ipcountry') ?? 'XX', // blob3
      ],
      // doubles: numeric measurements (double1–double20)
      doubles: [
        Date.now(),           // double1 — epoch ms (AE timestamps are separate)
      ],
      indexes: [url.pathname], // optional shard key for partitioning
    });

    return new Response('ok');
  },
};
```

---

## Basic SQL API Query

```bash
CF_ACCOUNT_ID="..."
CF_API_TOKEN="..."

curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT blob1 AS method, count() AS requests FROM $api_events WHERE timestamp > NOW() - INTERVAL '\''1'\'' HOUR GROUP BY method ORDER BY requests DESC LIMIT 10"
  }'
```

Response shape:

```json
{
  "meta": [
    { "name": "method", "type": "String" },
    { "name": "requests", "type": "UInt64" }
  ],
  "data": [
    { "method": "GET", "requests": "4821" },
    { "method": "POST", "requests": "1203" }
  ],
  "rows": 2,
  "rows_before_limit_at_least": 2
}
```

---

## Time-Series Aggregation with `toStartOfInterval`

ClickHouse's `toStartOfInterval` buckets timestamps into fixed windows:

```sql
SELECT
  toStartOfInterval(timestamp, INTERVAL 5 MINUTE) AS bucket,
  blob2                                             AS path,
  count()                                           AS hits,
  quantile(0.95)(double1)                           AS p95_latency_ms
FROM $api_events
WHERE
  timestamp BETWEEN toDateTime('2026-08-23 00:00:00')
                AND toDateTime('2026-08-23 06:00:00')
  AND blob2 LIKE '/api/%'
GROUP BY bucket, path
ORDER BY bucket ASC, hits DESC
```

```ts
// Fetch from a Worker or backend service
async function queryAE(sql: string, accountId: string, token: string) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`AE SQL error: ${err}`);
  }
  return res.json();
}
```

---

## HAVING and Filtered Aggregation

Use `HAVING` to eliminate low-traffic paths from error-rate dashboards:

```sql
SELECT
  blob2                             AS path,
  countIf(double2 >= 500)           AS errors,
  count()                           AS total,
  round(errors / total * 100, 2)    AS error_pct
FROM $api_events
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY path
HAVING total > 100
ORDER BY error_pct DESC
LIMIT 20
```

`double2` here stores the HTTP response status code written by the Worker.

---

## Sampling and Row Limits

Analytics Engine automatically samples at high ingest rates. Queries return a
`_sample_interval` column you can use to un-sample counts:

```sql
SELECT
  blob3              AS country,
  sum(count() * _sample_interval) AS estimated_requests
FROM $api_events
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY country
ORDER BY estimated_requests DESC
```

Raw event queries (no aggregation) are capped at **100,000 rows** per response. For full
exports, paginate using `timestamp < <last_seen_ts>` as a cursor.

---

## Anti-patterns

- Querying with `SELECT *` on a high-ingest dataset — returns only blobs and doubles as
  `blob1`…`blob20`, `double1`…`double20` columns; no column names unless aliased.
- Storing high-cardinality values (UUIDs, full URLs with query strings) in `indexes[]` —
  the index is a shard key, not a secondary index; high cardinality wastes storage.
- Using `double1`…`doubleN` for epoch milliseconds and also wanting sub-millisecond
  precision — doubles are IEEE 754 float64; precision loss begins around 2^53 ms.
- Issuing queries from a Worker bound to AE without caching results — each SQL API call
  is a full scan and counts toward account rate limits.

---

## Gotchas

- Dataset names are **case-sensitive** and must match the binding's `dataset` value in
  `wrangler.toml` exactly; `$Api_Events` ≠ `$api_events`.
- `timestamp` in AE is the server-side ingest time, not `double1` (client-supplied time).
  Never use `double1` as a primary time filter unless you also have a `timestamp` clause.
- The SQL API accepts only `POST`; `GET` with a query param returns `405`.
- Data retention is **90 days** on paid plans, **30 days** on Workers Free. Queries
  silently return empty results past the retention window — not an error.
- `quantile()` and other statistical aggregates require at least 1 data point; they
  return `NULL` on empty sets, which breaks JSON serialization in some clients.

---

## Verification

```bash
# Quick smoke-test: count events from the last hour
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT count() FROM $api_events WHERE timestamp > NOW() - INTERVAL '\''1'\'' HOUR"}' \
  | jq '.data[0]'

# Verify _sample_interval is 1 (no sampling in effect at low ingest)
curl -s -X POST ... \
  -d '{"query": "SELECT _sample_interval, count() FROM $api_events WHERE timestamp > NOW() - INTERVAL '\''5'\'' MINUTE GROUP BY _sample_interval"}' \
  | jq '.data'
```

---

## Related

- `cloudflare-workers-analytics-engine-custom-metrics.md`
- `workers-analytics-engine-graphql-api-querying.md`
- `workers-analytics-engine.md`
- `workers-tail-workers.md`
- `workers-observability-logs-metrics-2026.md`

---

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/reference/
- https://developers.cloudflare.com/analytics/analytics-engine/get-started/
- https://clickhouse.com/docs/en/sql-reference/functions/date-time-functions
