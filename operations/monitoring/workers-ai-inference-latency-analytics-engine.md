# Workers AI Inference Latency Tracking with Analytics Engine

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Workers AI model calls (text generation, embeddings, image classification) show p99 latency spikes that are invisible to request-level monitoring because the slow tail is masked by aggregated averages. You need per-model, per-prompt-size latency histograms retained over days without shipping raw logs to a third-party APM.

## Context

Workers AI exposes no built-in latency histogram. Every `env.AI.run()` call is a subrequest whose duration must be measured at the application layer and written into Analytics Engine for later querying via the SQL API. The key dimensions are model name, input token bucket, and cold-start vs warm status inferred from overall request latency.

## 1. Instrument the AI Call

Wrap every `env.AI.run()` call in a timing helper that writes a data point immediately after the response resolves.

```typescript
// src/ai-tracker.ts
export interface Env {
  AI: Ai;
  INFERENCE_METRICS: AnalyticsEngineDataset;
}

export async function trackedAiRun(
  env: Env,
  model: string,
  inputs: Record<string, unknown>,
  promptTokens: number
): Promise<unknown> {
  const start = Date.now();
  let status = "ok";
  try {
    const result = await env.AI.run(model as Parameters<Ai["run"]>[0], inputs as any);
    return result;
  } catch (err) {
    status = "error";
    throw err;
  } finally {
    const latencyMs = Date.now() - start;
    env.INFERENCE_METRICS.writeDataPoint({
      blobs: [model, status, tokenBucket(promptTokens)],
      doubles: [latencyMs, promptTokens],
      indexes: [model],
    });
  }
}

function tokenBucket(tokens: number): string {
  if (tokens < 128) return "xs";
  if (tokens < 512) return "sm";
  if (tokens < 2048) return "md";
  if (tokens < 8192) return "lg";
  return "xl";
}
```

## 2. wrangler.toml Binding

```toml
[[analytics_engine_datasets]]
binding = "INFERENCE_METRICS"
dataset = "workers_ai_latency"
```

## 3. Query Latency Percentiles via SQL API

Call the Analytics Engine SQL API from a dashboard Worker or cron job.

```typescript
// src/latency-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const DATASET = "workers_ai_latency";
const API_TOKEN = "<CF_API_TOKEN>";

export async function fetchP99ByModel(): Promise<Record<string, number>> {
  const sql = `
    SELECT
      blob1 AS model,
      quantileWeighted(0.99)(double1, 1) AS p99_ms,
      quantileWeighted(0.95)(double1, 1) AS p95_ms,
      count() AS total_calls
    FROM ${DATASET}
    WHERE timestamp > now() - INTERVAL '1' HOUR
      AND blob2 = 'ok'
    GROUP BY model
    ORDER BY p99_ms DESC
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  const data = (await resp.json()) as { data: Array<{ model: string; p99_ms: number }> };
  return Object.fromEntries(data.data.map((r) => [r.model, r.p99_ms]));
}
```

## 4. Alert on Latency Budget Burn

Define a latency SLO (e.g. p99 < 3000 ms) and send an alert when it burns.

```typescript
// src/latency-alert.ts
import { fetchP99ByModel } from "./latency-query";

const LATENCY_SLO_MS: Record<string, number> = {
  "@cf/meta/llama-3.1-8b-instruct": 3000,
  "@cf/baai/bge-base-en-v1.5": 500,
  "@cf/stabilityai/stable-diffusion-xl-base-1.0": 8000,
};

export async function checkLatencySlo(
  webhookUrl: string
): Promise<void> {
  const p99 = await fetchP99ByModel();
  const violations: string[] = [];

  for (const [model, slo] of Object.entries(LATENCY_SLO_MS)) {
    const actual = p99[model] ?? 0;
    if (actual > slo) {
      violations.push(`${model}: p99=${actual}ms > SLO=${slo}ms`);
    }
  }

  if (violations.length > 0) {
    await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: `Workers AI latency SLO breach:\n${violations.join("\n")}`,
      }),
    });
  }
}
```

## 5. Cron Trigger for Continuous Evaluation

```typescript
// src/index.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    await checkLatencySlo(env.ALERT_WEBHOOK_URL);
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml
[triggers]
crons = ["*/5 * * * *"]
```

## 6. Token-Size Breakdown Query

```sql
SELECT
  blob1 AS model,
  blob3 AS token_bucket,
  quantileWeighted(0.50)(double1, 1) AS p50_ms,
  quantileWeighted(0.99)(double1, 1) AS p99_ms,
  count() AS calls
FROM workers_ai_latency
WHERE timestamp > now() - INTERVAL '24' HOUR
GROUP BY model, token_bucket
ORDER BY model, token_bucket
```

## Anti-patterns

- **Logging latency only on success**: errors also consume quota and latency budget; always write in `finally`.
- **Using wall-clock `Date.now()` outside the Worker scope**: in Workers, `Date.now()` is available but can be frozen during I/O in some runtimes; measure the delta, not absolute timestamps.
- **High-cardinality blob fields**: do not use raw prompt text as a blob index — it blows Analytics Engine dataset cardinality limits.
- **Skipping token bucketing**: unbucketed token counts create hundreds of distinct series, making aggregation meaningless.

## Gotchas

- Analytics Engine writes are best-effort and fire-and-forget; a failed write does not propagate an exception to the Worker.
- The SQL API `quantileWeighted` function requires a weight argument; pass `1` as the weight when all samples are equal.
- Workers AI model names are case-sensitive in the blob field; normalise to lowercase before writing.
- Cold start attribution is not directly available from `env.AI.run()`; correlate with the outer request's `cf.colo` field if needed.

## Verification

1. Deploy the Worker, send 50 test requests with varied prompt sizes.
2. Wait 2 minutes, then query the SQL API with the p99 query above and confirm rows exist.
3. Temporarily lower `LATENCY_SLO_MS` to `1` and run the cron manually; confirm the webhook fires.
4. Restore SLO thresholds and verify no false alerts over a 1-hour window.

## Related

- `workers-ai-anomaly-detection-analytics-engine.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `slo-alerting-burn-rate.md`

## Sources

- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
