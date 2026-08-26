# Real-time Anomaly Detection Using Analytics Engine + Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You want to automatically detect when a metric (request rate, error rate, latency) deviates significantly from its recent baseline without manually setting fixed thresholds. Seasonality and gradual growth make static thresholds obsolete. You need a system that learns the rolling baseline, flags statistical anomalies, deduplicates alerts, and stores anomaly events for audit — all inside Cloudflare Workers.

## Context

Analytics Engine's SQL API supports aggregate functions (`avg`, `stddev_pop`) over time-series data written from Workers. A cron-triggered Worker queries rolling statistics, applies a z-score threshold, and emits anomaly events to D1. KV provides a deduplication cache to prevent alert storms. The baseline window is configurable; 1 hour of 5-minute buckets works well for intra-day traffic patterns.

## Solution

### wrangler.toml

```toml
name = "anomaly-detector"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "METRICS"
dataset = "workers_request_metrics"

[[d1_databases]]
binding = "ANOMALY_DB"
database_name = "anomaly_events"
database_id   = "YOUR_D1_DATABASE_ID"

[[kv_namespaces]]
binding = "DEDUP_KV"
id      = "YOUR_KV_NAMESPACE_ID"

[[triggers]]
crons = ["*/5 * * * *"]

[vars]
CF_ACCOUNT_ID  = "YOUR_ACCOUNT_ID"
CF_API_TOKEN_SECRET = "bound_via_secret"
Z_SCORE_THRESHOLD   = "3.0"
SLACK_WEBHOOK       = "https://hooks.slack.com/services/XXX"
```

### Metric write from request handler

```typescript
// src/metrics.ts

interface Env {
  METRICS: AnalyticsEngineDataset;
}

export interface RequestMetric {
  route: string;
  statusCode: number;
  durationMs: number;
  region: string;
}

// indexes[0] = route, indexes[1] = region
// doubles[0] = status code, doubles[1] = duration ms, doubles[2] = error flag (0/1)
export function writeRequestMetric(env: Env, metric: RequestMetric) {
  env.METRICS.writeDataPoint({
    indexes: [metric.route, metric.region],
    doubles: [
      metric.statusCode,
      metric.durationMs,
      metric.statusCode >= 500 ? 1 : 0,
    ],
  });
}
```

### Analytics Engine SQL for rolling statistics

```typescript
// src/query.ts

export interface MetricStats {
  route: string;
  bucketAvg: number;
  bucketStddev: number;
  currentValue: number;
  zScore: number;
}

export async function fetchAnomalyStats(
  accountId: string,
  apiToken: string,
  dataset: string,
  windowMinutes = 60,
  currentWindowMinutes = 5
): Promise<MetricStats[]> {
  // Query 1: baseline stats over the rolling window (excluding most recent bucket)
  const baselineSQL = `
    SELECT
      index1 AS route,
      avg(double2)    AS avg_latency,
      stddev_pop(double2) AS stddev_latency
    FROM ${dataset}
    WHERE timestamp > NOW() - INTERVAL '${windowMinutes}' MINUTE
      AND timestamp < NOW() - INTERVAL '${currentWindowMinutes}' MINUTE
      AND double2 > 0
    GROUP BY route
  `;

  // Query 2: current bucket metric value
  const currentSQL = `
    SELECT
      index1 AS route,
      avg(double2) AS current_latency
    FROM ${dataset}
    WHERE timestamp > NOW() - INTERVAL '${currentWindowMinutes}' MINUTE
      AND double2 > 0
    GROUP BY route
  `;

  const [baselineRes, currentRes] = await Promise.all([
    queryAnalyticsEngine(accountId, apiToken, baselineSQL),
    queryAnalyticsEngine(accountId, apiToken, currentSQL),
  ]);

  type BaselineRow = { route: string; avg_latency: number; stddev_latency: number };
  type CurrentRow  = { route: string; current_latency: number };

  const baselineMap = new Map<string, BaselineRow>(
    (baselineRes.data as BaselineRow[]).map(r => [r.route, r])
  );

  const results: MetricStats[] = [];
  for (const curr of currentRes.data as CurrentRow[]) {
    const baseline = baselineMap.get(curr.route);
    if (!baseline || baseline.stddev_latency === 0) continue;

    const zScore = (curr.current_latency - baseline.avg_latency) / baseline.stddev_latency;
    results.push({
      route: curr.route,
      bucketAvg: baseline.avg_latency,
      bucketStddev: baseline.stddev_latency,
      currentValue: curr.current_latency,
      zScore,
    });
  }
  return results;
}

async function queryAnalyticsEngine(
  accountId: string,
  apiToken: string,
  sql: string
): Promise<{ data: unknown[] }> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  if (!res.ok) {
    throw new Error(`Analytics Engine query failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<{ data: unknown[] }>;
}
```

### D1 anomaly event storage

```sql
-- migrations/0001_anomaly_events.sql

CREATE TABLE IF NOT EXISTS anomaly_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  metric      TEXT    NOT NULL,
  route       TEXT    NOT NULL,
  z_score     REAL    NOT NULL,
  current_val REAL    NOT NULL,
  baseline_avg  REAL  NOT NULL,
  baseline_std  REAL  NOT NULL,
  detected_at INTEGER NOT NULL,
  alerted     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_anomaly_route_time ON anomaly_events (route, detected_at);
```

### Alert deduplication with KV

```typescript
// src/dedup.ts

const DEDUP_TTL_SECONDS = 60 * 30; // suppress duplicate alerts for 30 minutes

export async function isAlertSuppressed(
  kv: KVNamespace,
  key: string
): Promise<boolean> {
  return (await kv.get(key)) !== null;
}

export async function suppressAlert(
  kv: KVNamespace,
  key: string
): Promise<void> {
  await kv.put(key, '1', { expirationTtl: DEDUP_TTL_SECONDS });
}

export function dedupKey(route: string, metric: string): string {
  return `anomaly:${metric}:${route}`;
}
```

### Main cron handler

```typescript
// src/index.ts

import { fetchAnomalyStats } from './query';
import { isAlertSuppressed, suppressAlert, dedupKey } from './dedup';

interface Env {
  METRICS: AnalyticsEngineDataset;
  ANOMALY_DB: D1Database;
  DEDUP_KV: KVNamespace;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN_SECRET: string;
  Z_SCORE_THRESHOLD: string;
  SLACK_WEBHOOK: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(detectAnomalies(env));
  },
} satisfies ExportedHandler<Env>;

async function detectAnomalies(env: Env) {
  const threshold = parseFloat(env.Z_SCORE_THRESHOLD);

  const stats = await fetchAnomalyStats(
    env.CF_ACCOUNT_ID,
    env.CF_API_TOKEN_SECRET,
    'workers_request_metrics'
  );

  for (const stat of stats) {
    if (Math.abs(stat.zScore) < threshold) continue;

    // Persist the anomaly regardless of dedup
    await env.ANOMALY_DB.prepare(`
      INSERT INTO anomaly_events
        (metric, route, z_score, current_val, baseline_avg, baseline_std, detected_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).bind(
      'latency',
      stat.route,
      stat.zScore,
      stat.currentValue,
      stat.bucketAvg,
      stat.bucketStddev,
      Date.now()
    ).run();

    // Check dedup before alerting
    const key = dedupKey(stat.route, 'latency');
    if (await isAlertSuppressed(env.DEDUP_KV, key)) continue;

    await sendSlackAlert(env.SLACK_WEBHOOK, stat);
    await suppressAlert(env.DEDUP_KV, key);
  }
}

async function sendSlackAlert(
  webhook: string,
  stat: import('./query').MetricStats
) {
  const direction = stat.zScore > 0 ? 'spike' : 'drop';
  const text =
    `*Anomaly detected*: Latency ${direction} on \`${stat.route}\`\n` +
    `Current: ${stat.currentValue.toFixed(1)}ms | ` +
    `Baseline: ${stat.bucketAvg.toFixed(1)}ms ± ${stat.bucketStddev.toFixed(1)}ms | ` +
    `Z-score: ${stat.zScore.toFixed(2)}`;

  await fetch(webhook, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
}
```

## Implementation Details

- **Z-score threshold**: A threshold of 3.0 flags values more than 3 standard deviations from the mean. For noisy metrics, raise to 4.0. For strict SLOs, lower to 2.5.
- **Minimum data requirement**: Do not compute z-scores when `stddev = 0` (all values identical) or when the baseline window contains fewer than 10 data points. Guard both cases.
- **Negative anomalies**: A large negative z-score (traffic drop) can indicate an upstream failure or routing issue. Alert on `|z| > threshold`, not just `z > threshold`.
- **Separate metric channels**: Run independent anomaly scans per metric (latency, error rate, request count) rather than a combined score. Mixed metrics obscure root cause.
- **Dedup window vs. incident duration**: A 30-minute KV suppression window works for transient spikes. For sustained incidents, use a separate incident-open state in D1 and only re-alert after the anomaly resolves.

## Anti-patterns

- **Fixed thresholds**: Static `latency > 500ms` rules break as traffic patterns evolve. Z-score baselines self-adjust to seasonal changes.
- **Including the current window in the baseline**: Averaging the anomalous bucket into the baseline inflates the mean and depresses the z-score. Always exclude the evaluation period from the baseline calculation.
- **Alerting on every cron run**: Without KV deduplication, a sustained anomaly generates an alert every 5 minutes. Suppress duplicate alerts within the incident window.
- **Single-bucket baselines**: One prior 5-minute bucket is not a meaningful baseline. Use at least 12 buckets (1 hour) to get a stable mean and standard deviation.

## Gotchas

- Analytics Engine SQL `stddev_pop` returns `0` when all values in the group are identical (e.g. constant synthetic traffic). Guard against division by zero.
- The Analytics Engine REST API requires an account-level API token with `Analytics:Read` permission, not the default Workers token.
- `NOW()` in Analytics Engine SQL is the query execution time in UTC. Time zone offsets are not supported in interval arithmetic.
- KV `put` with `expirationTtl` requires a minimum of 60 seconds. Values shorter than 60 will be rejected.
- D1 `run()` does not return the inserted row ID by default. Use `meta.last_row_id` from the result if you need it.

## Verification

```bash
# Apply D1 migration
npx wrangler d1 migrations apply anomaly_events

# Trigger cron manually
npx wrangler dev --test-scheduled
curl 'http://localhost:8787/__scheduled?cron=*/5+*+*+*+*'

# Query stored anomalies
npx wrangler d1 execute anomaly_events \
  --command "SELECT * FROM anomaly_events ORDER BY detected_at DESC LIMIT 10;"

# Check dedup state
npx wrangler kv key get --binding DEDUP_KV 'anomaly:latency:/api/users'
```

## Related

- `documentation/docs/policies/monitoring/workers-structured-logging-analytics-engine.md`
- `documentation/docs/policies/monitoring/workers-error-budget-tracking-d1.md`
- `documentation/docs/policies/monitoring/workers-uptime-monitor-cron-kv.md`
- `documentation/docs/policies/monitoring/workers-distributed-trace-propagation.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/api/
- https://en.wikipedia.org/wiki/Standard_score
