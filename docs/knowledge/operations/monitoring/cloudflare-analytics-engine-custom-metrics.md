# Cloudflare Analytics Engine for custom metrics

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The team needs per-route p99 latency, device-type error rates, and
custom business metrics (trial conversions, feature flag exposures)
from Cloudflare Workers without routing events to an external
pipeline on every request. Third-party metric ingestion adds per-
request latency and per-event cost that makes high-frequency
instrumentation prohibitive.

## Context

Cloudflare Workers Analytics Engine (WAE) is a write-optimised
time-series store built into the Workers runtime. Workers write data
points via a binding — no external HTTP call, no added latency.
Data is queryable via the Analytics Engine SQL API. The free tier
includes 1 million data point writes per day and 1 million SQL API
row reads per day. WAE is not a full observability backend; it is
the right tool for high-cardinality, high-frequency custom metrics
that would be prohibitively expensive in a per-event SaaS.

## Data model: blobs, doubles, and indexes

Each data point carries up to 20 string fields (`blob1`–`blob20`),
20 numeric fields (`double1`–`double20`), one `indexes` array (the
partition key), and a system-generated `timestamp`.

| Field      | Count | Type    | Use for                         |
|------------|-------|---------|---------------------------------|
| `blobN`    | 20    | string  | Labels: route, method, country  |
| `doubleN`  | 20    | float64 | Latency, byte count, flag (0/1) |
| `indexes`  | 1     | string[]| Partition key — e.g. tenant_id  |
| `timestamp`| —     | auto    | Write time (UTC, auto-set)      |

Choose `indexes` deliberately: it is the primary partition key.
Good defaults are `tenant_id` or `colo` so queries filter to one
partition without scanning all rows.

## Worker binding and write API

```toml
# wrangler.toml
[[analytics_engine_datasets]]
binding = "AE"
dataset = "prod_metrics"
```

```typescript
// src/middleware/metrics.ts
export function recordRequest(
  request: Request,
  response: Response,
  durationMs: number,
  env: Env,
): void {
  const url = new URL(request.url);
  env.AE.writeDataPoint({
    blobs: [
      url.pathname,                       // blob1: route
      request.method,                     // blob2: method
      getDeviceType(request.headers),     // blob3: device type
      request.cf?.country ?? 'unknown',   // blob4: country
    ],
    doubles: [
      durationMs,                         // double1: latency ms
      response.status >= 400 ? 1 : 0,    // double2: is_error
      response.status >= 500 ? 1 : 0,    // double3: is_5xx
    ],
    indexes: [request.cf?.colo ?? 'unknown'],
  });
}
```

`writeDataPoint` is non-blocking and does not add to response
latency. Call it after the response is constructed.

## SQL API queries

```bash
# Per-route p99 latency, last hour
curl "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  --data-urlencode "query=
    SELECT
      blob1                            AS route,
      quantile(0.50)(double1)          AS p50_ms,
      quantile(0.99)(double1)          AS p99_ms,
      count()                          AS requests
    FROM prod_metrics
    WHERE timestamp > NOW() - INTERVAL '1' HOUR
    GROUP BY route
    ORDER BY p99_ms DESC
    LIMIT 20
  "
```

```sql
-- Device-type error rates, last 24 hours
SELECT
  blob3                                       AS device_type,
  sum(double2)                                AS errors,
  count()                                     AS total,
  round(sum(double2) / count() * 100, 2)     AS error_pct
FROM prod_metrics
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY device_type
ORDER BY error_pct DESC;

-- Custom business metric: trial conversions per country
SELECT
  toStartOfHour(timestamp) AS hour,
  blob4                    AS country,
  sum(double1)             AS conversions
FROM trial_events
WHERE timestamp > NOW() - INTERVAL '7' DAY
  AND blob1 = 'trial_converted'
GROUP BY hour, country
ORDER BY hour DESC;
```

WAE uses a ClickHouse-compatible SQL dialect. Standard aggregates
(`count`, `sum`, `avg`, `quantile`) are available.

## Cost model

| Tier    | Daily writes     | SQL reads/day    | Price         |
|---------|------------------|------------------|---------------|
| Free    | 1 M data points  | 1 M rows         | $0            |
| Paid    | 10 M included    | 10 M included    | $5/month      |
| Overage | —                | —                | $0.25/M write |

At 1 000 req/s, one data point per request yields 86.4 M writes per
day — into the paid tier. Batch low-priority metrics with Durable
Objects: accumulate counters in memory, flush one data point per
minute per instance.

## Anti-patterns

- **Writing one data point per sub-operation** — WAE is designed for
  one data point per request; use OTel for distributed tracing.
- **High-cardinality values in blob fields** — user IDs, UUIDs, and
  full URLs in blobs explode storage; put partition keys in
  `indexes` instead.
- **Real-time alerting from WAE** — WAE has eventual consistency
  with 1–5 min data-available latency; not suitable for sub-minute
  SLO alerts.
- **PII in blob fields** — WAE data is queryable by anyone with
  Account Analytics Read; never write email or user IDs as blobs.

## Gotchas

- Use `quantile(0.99)(double1)` directly in SQL for simple doubles.
  `quantilesMerge` requires the `quantilesState` combinators at
  write time (ClickHouse pattern not applicable here).
- Maximum 20 blobs and 20 doubles per data point; extras are
  silently truncated.
- WAE is append-only; corrections require a new data point with a
  correction flag — there is no UPDATE or DELETE.
- The SQL API has a 5-second query timeout. Aggregations over large
  windows with high cardinality may time out.

## Verification

- `writeDataPoint` is called after response construction, not inside
  the critical response path.
- SQL queries return expected row counts against a staging dataset.
- Blob cardinality is documented; no field exceeds 1 000 distinct
  values in production data.
- Daily write volume is tracked; an alert fires before the free
  tier limit is reached.
- PII audit confirms no email or user ID in any blob field.

## Related

- `documentation/docs/policies/monitoring/cloudflare-analytics-engine.md`
- `documentation/docs/policies/monitoring/cloudflare-workers-analytics.md`
- `documentation/docs/policies/monitoring/metrics-vs-logs-vs-traces.md`
- `documentation/docs/policies/monitoring/cost-monitoring-dashboards.md`
- `documentation/docs/policies/cloudflare/workers-bindings.md`

## Source URLs (verified 2026-08-17)

- WAE getting started —
  https://developers.cloudflare.com/analytics/analytics-engine/
- WAE SQL API reference —
  https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- WAE limits and pricing —
  https://developers.cloudflare.com/analytics/analytics-engine/limits/
- WAE Worker binding API —
  https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
