# Workers AI Model Fallback Error-Rate Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Workers AI integration calls a primary model (e.g. `@cf/meta/llama-3.1-8b-instruct`) and falls back to a smaller or alternative model on error. Fallback triggers are invisible in standard logs: the user gets a response, but from the wrong model, with degraded quality and potentially different cost characteristics. You need per-model error rates, fallback trigger frequency, and cost deviation to detect silent model degradation and misconfigured fallback chains.

## Context

Cloudflare Workers AI exposes models through `env.AI.run()`. Errors include capacity limits (`429`), model unavailability (`503`), timeout, and malformed-output errors. A typical production pattern chains two or three models: primary → secondary → lightweight fallback. Without explicit instrumentation each hop is invisible. Analytics Engine lets you record which model was actually used, what error prompted the fallback, and the resulting token counts — giving you a per-model SLI and cost-attribution rollup without a separate observability backend.

---

## 1. Instrumented AI Wrapper with Fallback Chain

```typescript
// src/lib/ai-with-fallback.ts
import type { Ai, AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface AiCallOptions {
  ai: Ai;
  ae: AnalyticsEngineDataset;
  prompt: string;
  models: string[];          // ordered: primary, secondary, fallback...
  maxTokens?: number;
  requestId: string;
}

export interface AiCallResult {
  text: string;
  modelUsed: string;
  fallbackDepth: number;     // 0 = primary, 1 = first fallback, etc.
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
}

export async function runWithFallback(opts: AiCallOptions): Promise<AiCallResult> {
  const { ai, ae, prompt, models, maxTokens = 512, requestId } = opts;

  let lastError: unknown;

  for (let depth = 0; depth < models.length; depth++) {
    const model = models[depth];
    const t0 = Date.now();

    try {
      const response = await ai.run(model as Parameters<typeof ai.run>[0], {
        messages: [{ role: 'user', content: prompt }],
        max_tokens: maxTokens,
      });

      const latencyMs = Date.now() - t0;
      const text = (response as { response: string }).response;
      // Workers AI does not expose token counts in all models; estimate from chars
      const inputTokens  = Math.ceil(prompt.length / 4);
      const outputTokens = Math.ceil(text.length / 4);

      ae.writeDataPoint({
        indexes: [model],
        blobs: ['ok', requestId, depth === 0 ? 'primary' : 'fallback'],
        doubles: [latencyMs, inputTokens, outputTokens, depth, 0 /* error=0 */],
      });

      return { text, modelUsed: model, fallbackDepth: depth, inputTokens, outputTokens, latencyMs };

    } catch (err: unknown) {
      const latencyMs = Date.now() - t0;
      const errMsg = (err as Error).message ?? 'unknown';
      const errCode = /429/.test(errMsg) ? 429 : /503/.test(errMsg) ? 503 : 500;

      ae.writeDataPoint({
        indexes: [model],
        blobs: ['error', requestId, String(errCode)],
        doubles: [latencyMs, 0, 0, depth, 1 /* error=1 */],
      });

      lastError = err;
      // Continue to next model in chain
    }
  }

  throw lastError;
}
```

---

## 2. Structured Request Handler Integration

```typescript
// src/index.ts
import { runWithFallback } from './lib/ai-with-fallback';

const MODEL_CHAIN = [
  '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
  '@cf/meta/llama-3.1-8b-instruct',
  '@cf/mistral/mistral-7b-instruct-v0.1',
];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json<{ prompt: string }>();
    const requestId   = crypto.randomUUID().slice(0, 16);

    const result = await runWithFallback({
      ai: env.AI,
      ae: env.AE_DATASET,
      prompt,
      models: MODEL_CHAIN,
      requestId,
    });

    return Response.json({
      text:          result.text,
      model:         result.modelUsed,
      fallbackDepth: result.fallbackDepth,
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## 3. Analytics Engine SQL Queries

```sql
-- Per-model error rate over the last 1 hour
SELECT
  index1                                             AS model,
  SUM(_sample_interval * double5)                    AS error_count,
  SUM(_sample_interval)                              AS total_calls,
  ROUND(SUM(_sample_interval * double5) * 100.0 /
    NULLIF(SUM(_sample_interval), 0), 2)             AS error_rate_pct
FROM ai_model_calls
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY model
ORDER BY error_rate_pct DESC;

-- Fallback depth distribution — how often each fallback level is used
SELECT
  index1            AS model,
  double4           AS fallback_depth,
  COUNT()           AS calls
FROM ai_model_calls
WHERE timestamp > NOW() - INTERVAL '6' HOUR
  AND blob1 = 'ok'
GROUP BY model, fallback_depth
ORDER BY model, fallback_depth;

-- Estimated token cost per model (using $0.11 / M tokens for illustration)
SELECT
  index1                                      AS model,
  SUM(_sample_interval * double2)             AS total_input_tokens,
  SUM(_sample_interval * double3)             AS total_output_tokens,
  ROUND(
    (SUM(_sample_interval * double2) + SUM(_sample_interval * double3)) *
    0.11 / 1000000, 4
  )                                           AS estimated_cost_usd
FROM ai_model_calls
WHERE timestamp > NOW() - INTERVAL '24' HOUR
  AND blob1 = 'ok'
GROUP BY model
ORDER BY estimated_cost_usd DESC;

-- Fallback trigger rate — fraction of successful calls that used a non-primary model
SELECT
  toStartOfHour(timestamp)                    AS hour,
  SUM(CASE WHEN double4 > 0 THEN _sample_interval ELSE 0 END) * 1.0 /
    NULLIF(SUM(_sample_interval), 0)          AS fallback_rate
FROM ai_model_calls
WHERE blob1 = 'ok'
  AND timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY hour
ORDER BY hour DESC;
```

---

## 4. Alert Worker — Error Rate and Fallback Spike Detection

```typescript
// alert-worker/ai-model-alert.ts
// Cron: */10 * * * *

const ERROR_RATE_THRESHOLD  = 0.05;  // 5% error rate on primary model
const FALLBACK_RATE_THRESHOLD = 0.15; // 15% fallback rate

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Check primary model error rate
    const errorSql = `
      SELECT index1 AS model,
             SUM(_sample_interval * double5) * 1.0 / NULLIF(SUM(_sample_interval), 0) AS error_rate
      FROM ai_model_calls
      WHERE timestamp > NOW() - INTERVAL '10' MINUTE
        AND double4 = 0  -- primary model only
      GROUP BY model HAVING error_rate > ${ERROR_RATE_THRESHOLD}
    `;

    // Check fallback rate
    const fallbackSql = `
      SELECT SUM(CASE WHEN double4 > 0 THEN _sample_interval ELSE 0 END) * 1.0 /
             NULLIF(SUM(_sample_interval), 0) AS fallback_rate
      FROM ai_model_calls
      WHERE timestamp > NOW() - INTERVAL '10' MINUTE AND blob1 = 'ok'
    `;

    const [errorRows, fallbackRows] = await Promise.all([
      cfAeQuery<{ model: string; error_rate: number }>(env, errorSql),
      cfAeQuery<{ fallback_rate: number }>(env, fallbackSql),
    ]);

    const alerts: string[] = [];

    for (const row of errorRows) {
      alerts.push(`Model ${row.model} error rate: ${(row.error_rate * 100).toFixed(1)}%`);
    }

    const fr = fallbackRows[0]?.fallback_rate ?? 0;
    if (fr > FALLBACK_RATE_THRESHOLD) {
      alerts.push(`Fallback rate ${(fr * 100).toFixed(1)}% exceeds threshold`);
    }

    if (alerts.length) {
      await sendSlackAlert(env.SLACK_WEBHOOK, {
        text: `Workers AI model alert:\n${alerts.join('\n')}`,
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 5. Model Health Dashboard Helper

```typescript
// src/lib/ai-health.ts
// Exposed via an internal /ai/health endpoint for ops dashboards.

export async function getModelHealth(
  env: Env
): Promise<{ model: string; errorRate: number; p99Ms: number; fallbackDepth: number }[]> {
  const sql = `
    SELECT index1 AS model,
           SUM(_sample_interval * double5) * 1.0 / NULLIF(SUM(_sample_interval), 0) AS error_rate,
           quantileWeighted(0.99)(double1, _sample_interval) AS p99_ms,
           AVG(double4) AS avg_fallback_depth
    FROM ai_model_calls
    WHERE timestamp > NOW() - INTERVAL '1' HOUR
    GROUP BY model ORDER BY model
  `;

  const rows = await cfAeQuery<{
    model: string; error_rate: number; p99_ms: number; avg_fallback_depth: number;
  }>(env, sql);

  return rows.map(r => ({
    model:        r.model,
    errorRate:    r.error_rate,
    p99Ms:        r.p99_ms,
    fallbackDepth: r.avg_fallback_depth,
  }));
}
```

---

## Anti-patterns

- **Logging only final outcomes** — if the fallback succeeds, the upstream model error is lost. Record each model attempt independently, win or fail.
- **Using a single `model` dimension for all calls** — without recording which fallback depth was used, you cannot separate primary-model cost from fallback-model cost.
- **Infinite retry on the same model** — retry + fallback are different strategies. Retry for transient errors on the same model; fallback for capacity/availability errors on a different model.
- **Not tracking input/output tokens separately** — input and output tokens are priced differently; aggregating them prevents accurate cost attribution.

## Gotchas

- Workers AI token counts are not always returned in the response object for all models; character-based estimation (`chars / 4`) is a coarse proxy but sufficient for trending.
- `env.AI.run()` throws on HTTP 429/503; the error message format may change between Workers AI API versions — pattern-match defensively.
- Some Workers AI models stream output; `runWithFallback` above assumes a non-streaming response. Streaming responses require adapting the wrapper to collect chunks before writing the data point.
- The fallback chain should be ordered from highest-quality to lowest — do not put a cheaper model first just because it is available, or quality degradation will go undetected.
- Analytics Engine `indexes` accept up to 512 bytes; model names like `@cf/meta/llama-3.3-70b-instruct-fp8-fast` are ~45 characters and are safe, but trim if you concatenate prefixes.

## Verification

```bash
# Trigger a fallback by temporarily pointing to a nonexistent model in dev
wrangler dev --local

# Query AE for fallback events in the last 10 minutes
curl -s "$CF_AE_SQL_URL" -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query":"SELECT index1, blob1, blob3, COUNT() FROM ai_model_calls WHERE timestamp > NOW() - INTERVAL '\''10'\'' MINUTE GROUP BY index1, blob1, blob3 ORDER BY COUNT() DESC"}' \
  | jq '.data'

# Verify error rate is captured correctly
curl -s "$CF_AE_SQL_URL" -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query":"SELECT index1, SUM(double5), SUM(_sample_interval) FROM ai_model_calls WHERE timestamp > NOW() - INTERVAL '\''1'\'' HOUR GROUP BY index1"}' \
  | jq '.data'
```

## Related

- `workers-ai-inference-cost-analytics-engine-tracking.md`
- `workers-ai-token-usage-budget-analytics-engine.md`
- `workers-ai-inference-latency-analytics-engine.md`
- `workers-ai-gateway-caching-monitoring.md`
- `workers-ai-anomaly-detection-analytics-engine.md`
- `slo-alerting-burn-rate.md`

## Sources

- Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- Workers AI error handling: https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
