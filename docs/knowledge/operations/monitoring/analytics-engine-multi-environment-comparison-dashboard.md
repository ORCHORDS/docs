# Analytics Engine Multi-Environment Comparison Dashboard

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

After deploying to staging you need to answer: "Does the p99 latency of the `/checkout` endpoint on staging match production's baseline from the same time yesterday?" Manual inspection of two separate dashboards with misaligned time ranges leads to errors. A single Analytics Engine dataset that tags every data point with an `environment` dimension lets you plot staging vs. production on the same axes, with automatic time-shift queries for before/after comparisons.

## Context

Cloudflare Analytics Engine stores time-series blobs written by Workers. Each blob can carry up to 20 double fields and 20 blob (string) fields. By adding an `environment` blob field (values: `production`, `staging`, `preview`) and a `region` blob field to every write, a single dataset covers all deployments. The Workers Analytics Engine SQL API then allows GROUP BY on those fields, enabling comparison queries in Grafana or any BI tool that speaks HTTP + JSON.

The comparison pattern has two modes:
1. **Live side-by-side**: plot the same metric for `production` and `staging` over the same wall-clock window.
2. **Time-shifted baseline**: plot today's `production` metric alongside yesterday's `production` at `now - 24h` — useful for detecting regressions introduced by today's deploy without access to a staging environment.

## Worker Instrumentation

```typescript
// src/metrics.ts
export interface Env {
  AE: AnalyticsEngineDataset;
  ENVIRONMENT: string;  // "production" | "staging" | "preview"
}

export interface RequestMetric {
  route: string;
  statusCode: number;
  durationMs: number;
  colo: string;
}

/**
 * Write one data point per request.
 * Use a stable index layout: double1 = duration_ms, double2 = status_code,
 * blob1 = environment, blob2 = route, blob3 = colo.
 */
export function writeRequestMetric(ae: AnalyticsEngineDataset, env: string, m: RequestMetric): void {
  ae.writeDataPoint({
    blobs:   [env, m.route, m.colo],
    doubles: [m.durationMs, m.statusCode],
    indexes: [m.route],
  });
}

// src/index.ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const colo = request.cf?.colo ?? 'unknown';
    const route = new URL(request.url).pathname;

    const response = await handleRequest(request, env);

    ctx.waitUntil(Promise.resolve().then(() => {
      writeRequestMetric(env.AE, env.ENVIRONMENT, {
        route,
        statusCode: response.status,
        durationMs: Date.now() - start,
        colo: String(colo),
      });
    }));

    return response;
  },
} satisfies ExportedHandler<Env>;

async function handleRequest(request: Request, env: Env): Promise<Response> {
  return new Response('ok');
}
```

```toml
# wrangler.toml (production)
name = "my-api"
main = "src/index.ts"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "request_metrics"

[vars]
ENVIRONMENT = "production"

# wrangler.toml (staging) — same dataset name, different env var
# Publish with: wrangler deploy --env staging
[env.staging.vars]
ENVIRONMENT = "staging"
```

## Analytics Engine SQL Queries for Comparison

```sql
-- Side-by-side p99 latency: production vs. staging, last 1 hour
-- blob1 = environment, blob2 = route, double1 = duration_ms

SELECT
  blob1                                          AS environment,
  blob2                                          AS route,
  quantileWeighted(0.99)(double1, _sample_interval) AS p99_ms,
  count()                                        AS requests
FROM request_metrics
WHERE
  timestamp >= NOW() - INTERVAL '1' HOUR
  AND blob2 = '/checkout'
GROUP BY environment, route
ORDER BY environment;
```

```sql
-- Time-shifted baseline: today's production vs. yesterday's production
-- Using a UNION with a time offset to align time windows

SELECT
  'today'    AS window,
  toStartOfFiveMinutes(timestamp)               AS bucket,
  quantileWeighted(0.99)(double1, _sample_interval) AS p99_ms
FROM request_metrics
WHERE
  blob1 = 'production'
  AND blob2 = '/checkout'
  AND timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY bucket

UNION ALL

SELECT
  'yesterday' AS window,
  -- Shift yesterday's timestamps forward 24 h so they align with today on the x-axis
  toStartOfFiveMinutes(timestamp + INTERVAL '1' DAY) AS bucket,
  quantileWeighted(0.99)(double1, _sample_interval)   AS p99_ms
FROM request_metrics
WHERE
  blob1 = 'production'
  AND blob2 = '/checkout'
  AND timestamp >= NOW() - INTERVAL '25' HOUR
  AND timestamp <  NOW() - INTERVAL '23' HOUR
GROUP BY bucket

ORDER BY bucket, window;
```

## Grafana Dashboard Setup

```typescript
// Grafana data source: Cloudflare Analytics Engine
// Method: POST https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql
// Auth header: Authorization: Bearer <token>

// Grafana JSON model fragment for the comparison panel:
const grafanaPanel = {
  type: 'timeseries',
  title: 'p99 Latency — Production vs Staging',
  datasource: { type: 'cloudflare-analytics-engine' },
  fieldConfig: {
    overrides: [
      { matcher: { id: 'byName', options: 'p99_ms {environment="production"}' },
        properties: [{ id: 'color', value: { mode: 'fixed', fixedColor: 'blue' } }] },
      { matcher: { id: 'byName', options: 'p99_ms {environment="staging"}' },
        properties: [{ id: 'color', value: { mode: 'fixed', fixedColor: 'orange' } }] },
    ],
  },
  options: {
    legend: { displayMode: 'table', placement: 'bottom', calcs: ['lastNotNull', 'max'] },
  },
};
```

```bash
# Query the API directly for testing
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT blob1 AS env, quantileWeighted(0.99)(double1, _sample_interval) AS p99 FROM request_metrics WHERE timestamp >= NOW() - INTERVAL '\''1'\'' HOUR GROUP BY env"
  }' | jq '.data'
```

## Alerting on Environment Divergence

```typescript
// src/divergence-check.ts
// A scheduled Worker that queries Analytics Engine every 5 minutes
// and fires an alert if staging p99 exceeds production p99 by more than 20%.

export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  ALERT_WEBHOOK: string;
  DATASET: string;
}

const DIVERGENCE_THRESHOLD = 1.20; // 20% above production baseline

async function queryP99(env: Env, environment: string): Promise<number> {
  const sql = `
    SELECT quantileWeighted(0.99)(double1, _sample_interval) AS p99
    FROM ${env.DATASET}
    WHERE blob1 = '${environment}'
      AND timestamp >= NOW() - INTERVAL '10' MINUTE
  `;
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  if (!res.ok) throw new Error(`AE query failed: ${res.status}`);
  const json = await res.json<{ data: Array<{ p99: number }> }>();
  return json.data[0]?.p99 ?? 0;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const [prodP99, stagingP99] = await Promise.all([
      queryP99(env, 'production'),
      queryP99(env, 'staging'),
    ]);

    if (stagingP99 > prodP99 * DIVERGENCE_THRESHOLD) {
      ctx.waitUntil(
        fetch(env.ALERT_WEBHOOK, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: `Staging p99 latency (${stagingP99.toFixed(1)} ms) exceeds production (${prodP99.toFixed(1)} ms) by >${Math.round((DIVERGENCE_THRESHOLD - 1) * 100)}%.`,
          }),
        })
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- **Separate datasets per environment**: Using `request_metrics_production` and `request_metrics_staging` as distinct dataset names prevents cross-environment GROUP BY queries and doubles dataset management overhead. One dataset with an `environment` dimension is the correct model.
- **Comparing raw counts instead of rates**: A staging environment typically receives lower traffic than production. Comparing absolute request counts is meaningless; always compare rates or percentile latencies, which are traffic-volume-independent.
- **Using wall-clock time for the time-shift baseline without accounting for traffic patterns**: Weekday production traffic at 14:00 UTC is not comparable to Sunday traffic at 14:00 UTC — 7 days. For accurate baselines, compare the same day-of-week or use a rolling median of the past N same-day-of-week windows.
- **Storing environment in a `double` field**: Environment names are strings. Storing them as integers (0 = prod, 1 = staging) breaks SQL readability and complicates filtering. Use a `blob` field.

## Gotchas

- **Analytics Engine dataset retention**: As of 2025, Analytics Engine retains data for 31 days. Time-shifted comparisons beyond 30 days will silently return empty result sets — add a `WHERE timestamp >= NOW() - INTERVAL '30' DAY` guard.
- **`_sample_interval` weighting**: Always use `quantileWeighted(p)(double1, _sample_interval)` rather than `quantile(p)(double1)`. High-traffic Workers use adaptive sampling; omitting the weight produces inaccurate percentiles for sampled datasets.
- **Schema index consistency**: The `indexes` field in `writeDataPoint` must contain the same type and positional values across all environments to avoid hot shard skew on Cloudflare's internal partitioning.
- **Preview deployments**: Cloudflare Pages preview deployments generate a unique `ENVIRONMENT` string per branch (e.g. `preview-abc123`). Use a `LIKE 'preview%'` filter rather than an exact match when you want to aggregate all preview environments.

## Verification

```bash
# Confirm data is flowing from both environments
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1 AS env, count() AS n FROM request_metrics WHERE timestamp >= NOW() - INTERVAL '\''5'\'' MINUTE GROUP BY env"}' \
  | jq '.data'

# Expected output: both "production" and "staging" rows with non-zero counts
```

## Related

- `cloudflare-analytics-engine.md` — Analytics Engine fundamentals
- `analytics-engine-sql-api-programmatic-querying.md` — SQL API usage patterns
- `cloudflare-analytics-engine-grafana-dashboard.md` — Grafana integration
- `canary-deployment-metric-baseline-comparison.md` — canary vs. production metric comparison patterns

## Sources

- Cloudflare Analytics Engine documentation: https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Grafana Cloudflare data source plugin: https://grafana.com/grafana/plugins/cloudflare-app/
