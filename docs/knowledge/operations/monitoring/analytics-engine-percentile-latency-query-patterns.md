# Analytics Engine Percentile Latency Query Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You write raw latency observations into Analytics Engine via `writeDataPoint` and
need p50/p75/p95/p99 breakdowns for dashboards and SLO burn-rate alerts — without
pre-bucketing into histograms before ingestion or pulling raw rows to a client for
local aggregation.

## Context

Analytics Engine's SQL API exposes a `quantileExact` family of aggregate functions
(ClickHouse-compatible). Unlike Prometheus histograms, AE stores individual
observations and computes exact quantiles at query time. The trade-off: query cost
scales linearly with row count, so high-cardinality windows benefit from
`quantileTDigest` (approximate, configurable compression). Both functions work over
arbitrary `GROUP BY` dimensions — per-route, per-colo, per-tenant — without schema
changes. Existing domain-specific articles (`d1-query-latency-histogram-analytics-engine`,
`workers-cpu-time-percentile-analytics-engine`) cover individual services; this
article documents the general query patterns reusable across any latency signal.

---

## Writing latency observations

```typescript
// src/middleware.ts — wrap any fetch handler
export async function withLatencyTracking(
  request: Request,
  env: Env,
  next: () => Promise<Response>
): Promise<Response> {
  const start = performance.now();
  const response = await next();
  const latencyMs = performance.now() - start;

  env.AE.writeDataPoint({
    blobs:   [new URL(request.url).pathname, request.cf?.colo ?? "unknown"],
    doubles: [latencyMs],
    indexes: [env.SERVICE_NAME],   // primary partition key for cost-efficient filtering
  });

  return response;
}
```

`blob[0]` = route prefix, `blob[1]` = colo, `double[0]` = latency_ms.
Keep doubles sparse — AE supports up to 20 but each adds per-row storage cost.
Use `index1` (not blob) as the primary WHERE filter; it is stored as a columnar
index and dramatically reduces query scan cost.

## Exact quantile query

```sql
-- Cloudflare Analytics Engine SQL API (POST to /accounts/:id/analytics_engine/sql)
SELECT
  blob1                          AS route,
  quantileExact(0.50)(double1)   AS p50_ms,
  quantileExact(0.75)(double1)   AS p75_ms,
  quantileExact(0.95)(double1)   AS p95_ms,
  quantileExact(0.99)(double1)   AS p99_ms,
  count()                        AS sample_count
FROM MY_AE_DATASET
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
  AND index1 = 'api-gateway'
GROUP BY route
ORDER BY p99_ms DESC
LIMIT 50;
```

Results reflect exact population quantiles for the window. The API returns `null`
for any group with zero matching rows — always `COALESCE` in downstream code.

## Approximate quantile for high-cardinality windows

```sql
-- quantileTDigest is O(1) memory; accuracy tunable via compression (default 100)
-- Syntax: quantileTDigest(compression)(level)(column)
SELECT
  blob2                                      AS colo,
  quantileTDigest(0.95)(double1)             AS p95_approx_ms,
  quantileTDigest(200)(0.99)(double1)        AS p99_high_acc_ms,
  count()                                    AS n
FROM MY_AE_DATASET
WHERE timestamp >= NOW() - INTERVAL '6' HOUR
GROUP BY colo
ORDER BY p99_high_acc_ms DESC;
```

Compression 200 keeps relative error below 0.1% for most realistic latency
distributions. Use this form for 6-hour or longer windows on high-traffic services
to avoid the 30-second API query timeout.

## Multi-percentile alerting via cron Worker

```typescript
// src/percentile-alert.ts — triggered on Workers cron schedule
export async function checkLatencySLO(env: Env): Promise<void> {
  const query = `
    SELECT
      COALESCE(quantileExact(0.95)(double1), 0) AS p95,
      COALESCE(quantileExact(0.99)(double1), 0) AS p99,
      count() AS n
    FROM MY_AE_DATASET
    WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
      AND index1 = ?
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      body: JSON.stringify({ query, parameters: [env.SERVICE_NAME] }),
    }
  );

  const { data } = await res.json<{ data: Array<{ p95: number; p99: number; n: number }> }>();
  if (!data.length || data[0].n < 10) return; // skip low-traffic windows

  const { p95, p99, n } = data[0];
  const alerts: string[] = [];
  if (p95 > 500)  alerts.push(`p95=${p95.toFixed(0)}ms > 500ms`);
  if (p99 > 2000) alerts.push(`p99=${p99.toFixed(0)}ms > 2000ms`);

  if (alerts.length) {
    await env.ALERT_QUEUE.send({ service: env.SERVICE_NAME, alerts, sampleSize: n });
  }
}
```

## SLO breach ratio for burn-rate calculation

```sql
-- Count requests above threshold instead of computing quantile
-- Use breach_ratio in burn-rate formulae (see slo-alerting-burn-rate.md)
SELECT
  countIf(double1 > 1000)                         AS breach_count,
  count()                                          AS total_count,
  countIf(double1 > 1000) / count()               AS breach_ratio,
  quantileExact(0.99)(double1)                     AS p99_ms
FROM MY_AE_DATASET
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
  AND index1 = 'checkout-api'
```

`breach_ratio > 0.05` means more than 5% of requests exceed the 1 s threshold —
combine with a 6-hour window query to detect fast vs. slow burn-rate SLO alerts.

## Multi-window percentile comparison

```sql
-- Detect regressions by comparing current vs. prior window
SELECT
  quantileExact(0.99)(double1) AS p99_current
FROM MY_AE_DATASET
WHERE timestamp >= NOW() - INTERVAL '30' MINUTE AND index1 = 'api-gateway'
UNION ALL
SELECT
  quantileExact(0.99)(double1) AS p99_prior
FROM MY_AE_DATASET
WHERE timestamp BETWEEN NOW() - INTERVAL '90' MINUTE AND NOW() - INTERVAL '30' MINUTE
  AND index1 = 'api-gateway';
-- Application code divides current/prior; ratio > 1.5 = 50% regression
```

---

## Anti-patterns

- **Using `avg()` for latency SLOs**: mean hides tail behaviour. Outliers inflate
  the mean less than the p99, giving false confidence that things are fine.
- **GROUP BY on user IDs or request UUIDs**: unbounded cardinality causes query
  timeouts. Keep `GROUP BY` dimensions coarse (route prefix, colo, tier).
- **Polling the SQL API faster than 60 s**: AE ingestion has a 5–10 s propagation
  lag; sub-minute polling surfaces stale data without fresher signal.
- **Omitting `index1` in WHERE**: full dataset scans against all indexes are
  expensive and slow; always filter on `index1` for your service name first.

## Gotchas

- `quantileExact` buffers all matching rows in memory per group; on multi-million-row
  windows with many groups it will hit the 30 s timeout. Switch to `quantileTDigest`.
- AE SQL `?` parameters are positional. The `parameters` array must match `?` order
  exactly; named parameters are not supported.
- `NOW()` in AE SQL is UTC. Apply timezone offsets in the application layer, not in
  the query.
- AE retains data for 31 days by default; queries spanning more than 31 days return
  incomplete results without error.

## Verification

```bash
# Spot-check p99 for the last 10 minutes
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT COALESCE(quantileExact(0.99)(double1),0) AS p99, count() AS n FROM MY_AE_DATASET WHERE timestamp >= NOW() - INTERVAL '"'"'10'"'"' MINUTE AND index1 = '"'"'api-gateway'"'"'"}' \
  | jq '{p99: .data[0].p99, n: .data[0].n}'
```

Expected: `p99` is a positive number; `n` matches recent request count.
If `n = 0`, confirm the dataset name and that `writeDataPoint` is being called.

## Related

- `d1-query-latency-histogram-analytics-engine.md`
- `workers-cpu-time-percentile-analytics-engine.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `slo-alerting-burn-rate.md`
- `multiwindow-burn-rate-slo-alerts.md`

## Sources

- Cloudflare Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- ClickHouse quantile functions reference: https://clickhouse.com/docs/en/sql-reference/aggregate-functions/reference/quantile
- ClickHouse t-digest: https://clickhouse.com/docs/en/sql-reference/aggregate-functions/reference/quantiletdigest
- AE writeDataPoint limits: https://developers.cloudflare.com/analytics/analytics-engine/limits/
