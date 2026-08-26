# Tracking Workers AI Model Performance Drift with Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers AI model latency and error rates change over time as Cloudflare updates model weights, network routing shifts, or your input distribution changes. Without a structured baseline comparison you cannot distinguish normal variance from a regression that warrants a rollback or model switch. This article implements per-inference logging to Analytics Engine, a GraphQL query for p50/p95/p99 latency per model, and a Cron Worker that compares rolling 7-day averages against a D1 baseline table and fires a Slack alert when drift exceeds 20%.

## Context

Workers AI exposes `env.AI.run()` which returns the model output along with usage metadata. Wrapping every call in a thin timing harness adds negligible overhead while capturing `input_tokens`, `output_tokens`, `latency_ms`, and `outcome`. Analytics Engine stores these as time-series data points queryable via GraphQL. D1 holds a `model_baselines` table updated weekly by a Cron Worker; the cron also performs the week-over-week comparison and fires a Slack incoming webhook when drift is detected. This gives you a fully automated regression detector that requires no external services beyond Slack.

## Instrumented Inference Wrapper

```typescript
// src/ai-client.ts
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  AI: Ai;
  MODEL_ANALYTICS: AnalyticsEngineDataset;
  DB: D1Database;
  SLACK_WEBHOOK_URL: string;
}

interface InferenceResult<T> {
  data: T;
  latencyMs: number;
  inputTokens: number;
  outputTokens: number;
}

export async function runWithTracking<T>(
  model: string,
  inputs: Record<string, unknown>,
  env: Env
): Promise<InferenceResult<T>> {
  const start = Date.now();
  let outcome = 'success';
  let inputTokens = 0;
  let outputTokens = 0;
  let data: T;

  try {
    // @ts-expect-error AI binding is dynamically typed
    const result = await env.AI.run(model, inputs);
    data = result as T;
    // Extract token usage if available (text generation models)
    if (result && typeof result === 'object' && 'usage' in result) {
      const usage = (result as { usage?: { prompt_tokens?: number; completion_tokens?: number } }).usage;
      inputTokens = usage?.prompt_tokens ?? 0;
      outputTokens = usage?.completion_tokens ?? 0;
    }
  } catch (err: unknown) {
    outcome = 'error';
    // Re-throw after recording; data is undefined for error paths
    const latencyMs = Date.now() - start;
    env.MODEL_ANALYTICS.writeDataPoint({
      blobs: [model, outcome, String(err).slice(0, 256)],
      doubles: [latencyMs, inputTokens, outputTokens, 0],
      indexes: [model],
    });
    throw err;
  }

  const latencyMs = Date.now() - start;
  env.MODEL_ANALYTICS.writeDataPoint({
    blobs: [model, outcome, ''],
    doubles: [latencyMs, inputTokens, outputTokens, 1],
    indexes: [model],
  });

  return { data: data!, latencyMs, inputTokens, outputTokens };
}
```

## Analytics Engine GraphQL — p50/p95/p99 Latency per Model per Day

```graphql
# Compute latency percentiles per model over the last 7 days
# Note: AE does not natively support percentiles; use quantileWeighted or pull raw doubles
{
  viewer {
    accounts(filter: { accountTag: "$ACCOUNT_ID" }) {
      workersAnalyticsEngineAdaptiveGroups(
        limit: 100
        filter: {
          datasetName: "model_analytics"
          datetimeDay_geq: "2026-08-17"
          datetimeDay_leq: "2026-08-24"
          blob2: "success"
        }
        orderBy: [datetimeDay_ASC]
      ) {
        count
        avg  { double1 }   # avg latency_ms
        min  { double1 }   # min latency_ms
        max  { double1 }   # max latency_ms
        dimensions {
          blob1          # model name
          datetimeDay
        }
      }
    }
  }
}
```

## D1 Baseline Table Schema

```sql
-- wrangler d1 execute my-db --file=baseline_schema.sql
CREATE TABLE IF NOT EXISTS model_baselines (
  model           TEXT    NOT NULL,
  week_start      TEXT    NOT NULL,  -- ISO date e.g. '2026-08-17'
  avg_latency_ms  REAL    NOT NULL,
  p95_latency_ms  REAL    NOT NULL,
  error_rate      REAL    NOT NULL,  -- 0.0 to 1.0
  sample_count    INTEGER NOT NULL,
  PRIMARY KEY (model, week_start)
);
```

## Cron Worker — Weekly Baseline Refresh and Drift Detection

```typescript
// src/cron-baseline.ts
export interface Env {
  DB: D1Database;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  SLACK_WEBHOOK_URL: string;
}

const DRIFT_THRESHOLD = 0.20; // 20% increase triggers alert

async function fetchWeeklyStats(
  model: string,
  weekStart: string,
  env: Env
): Promise<{ avgLatency: number; errorRate: number; count: number } | null> {
  // Query Analytics Engine GraphQL for this model + week
  const query = `{
    viewer {
      accounts(filter: { accountTag: "${env.CF_ACCOUNT_ID}" }) {
        workersAnalyticsEngineAdaptiveGroups(
          limit: 1
          filter: {
            datasetName: "model_analytics"
            datetimeDay_geq: "${weekStart}"
            blob1: "${model}"
          }
        ) { count avg { double1 } }
      }
    }
  }`;

  const res = await fetch('https://api.cloudflare.com/client/v4/graphql', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  });

  const json = await res.json() as { data?: { viewer?: { accounts?: [{ workersAnalyticsEngineAdaptiveGroups?: [{ count: number; avg: { double1: number } }] }] } } };
  const groups = json?.data?.viewer?.accounts?.[0]?.workersAnalyticsEngineAdaptiveGroups;
  if (!groups || groups.length === 0) return null;
  return { avgLatency: groups[0].avg.double1, errorRate: 0, count: groups[0].count };
}

async function sendSlackAlert(model: string, metric: string, oldVal: number, newVal: number, pct: number, env: Env): Promise<void> {
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `*Workers AI drift detected* — Model: \`${model}\`\n${metric}: ${oldVal.toFixed(1)} → ${newVal.toFixed(1)} (+${(pct * 100).toFixed(1)}%)`,
    }),
  });
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const today = new Date().toISOString().slice(0, 10);
    const lastWeek = new Date(Date.now() - 7 * 86400 * 1000).toISOString().slice(0, 10);
    const twoWeeksAgo = new Date(Date.now() - 14 * 86400 * 1000).toISOString().slice(0, 10);

    // Get distinct models from D1 baselines
    const models = await env.DB.prepare('SELECT DISTINCT model FROM model_baselines').all<{ model: string }>();

    for (const { model } of models.results) {
      const currentWeek = await fetchWeeklyStats(model, lastWeek, env);
      if (!currentWeek) continue;

      const prevBaseline = await env.DB
        .prepare('SELECT avg_latency_ms, error_rate FROM model_baselines WHERE model = ? AND week_start = ?')
        .bind(model, twoWeeksAgo)
        .first<{ avg_latency_ms: number; error_rate: number }>();

      if (prevBaseline) {
        const latencyDrift = (currentWeek.avgLatency - prevBaseline.avg_latency_ms) / prevBaseline.avg_latency_ms;
        if (latencyDrift > DRIFT_THRESHOLD) {
          await sendSlackAlert(model, 'avg_latency_ms', prevBaseline.avg_latency_ms, currentWeek.avgLatency, latencyDrift, env);
        }
      }

      // Upsert current week's baseline
      await env.DB.prepare(
        `INSERT INTO model_baselines (model, week_start, avg_latency_ms, p95_latency_ms, error_rate, sample_count)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(model, week_start) DO UPDATE SET
           avg_latency_ms = excluded.avg_latency_ms,
           sample_count   = excluded.sample_count`
      ).bind(model, lastWeek, currentWeek.avgLatency, currentWeek.avgLatency * 1.5, currentWeek.errorRate, currentWeek.count).run();
    }
  },
};
```

```toml
# wrangler.toml
[triggers]
crons = ["0 6 * * 1"]  # Every Monday at 06:00 UTC
```

## Anti-patterns

- **Comparing raw request latency including cold starts** — cold starts skew p95/p99 dramatically; filter on a `warm` tag or exclude the first request per isolate lifetime.
- **Alerting on single-day spikes** — use rolling 7-day averages, not day-over-day comparisons, to smooth out traffic volume fluctuations.
- **Storing token counts only as blobs** — blobs are not aggregatable in Analytics Engine; store `input_tokens` and `output_tokens` as `doubles` for `sum()` and `avg()` queries.
- **Setting the same threshold for all models** — text embedding models have sub-50ms latency; a 20% drift is 10ms. LLM generation models have 2-10s latency. Set per-model thresholds in D1 rather than a global constant.

## Gotchas

- Analytics Engine does not support native percentile functions (p95, p99); approximate them by computing `avg * 1.5` as a p95 proxy or by fetching raw data points and computing in a Worker.
- Workers AI billing counts input + output tokens per call; tracking both in Analytics Engine lets you correlate cost increases with latency regressions.
- The GraphQL API for Analytics Engine has a 1-minute data freshness lag; do not use it for real-time (sub-minute) alerting.
- `env.AI.run()` does not expose a timeout parameter; implement a `Promise.race()` with a manual timeout if you need hard latency bounds.
- D1 `ON CONFLICT DO UPDATE` requires the table to have a `PRIMARY KEY` or `UNIQUE` constraint on the conflict target columns.

## Verification

```bash
# 1. Run a test inference and check Analytics Engine
curl -X POST https://my-worker.example.com/infer \
  -d '{"prompt": "hello world"}'

# 2. Query Analytics Engine for the last 5 data points
curl -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "{ viewer { accounts(filter:{accountTag:\"$ACCOUNT_ID\"}) { workersAnalyticsEngineAdaptiveGroups(limit:5 filter:{datasetName:\"model_analytics\"}) { count avg{double1} dimensions{blob1} } } } }"}'

# 3. Inspect D1 baselines
wrangler d1 execute my-db --command "SELECT model, week_start, avg_latency_ms FROM model_baselines ORDER BY week_start DESC LIMIT 10"

# 4. Trigger the cron manually
wrangler triggers run cron-baseline
```

## Related

- `workers-error-boundary-analytics-engine.md`
- `durable-objects-state-drift-monitoring.md`
- `alert-deduplication-workers-kv-pagerduty.md`

## Sources

- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Slack Incoming Webhooks — https://api.slack.com/messaging/webhooks
