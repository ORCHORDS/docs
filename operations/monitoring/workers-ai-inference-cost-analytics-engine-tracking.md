# Workers AI Inference Cost Analytics Engine Tracking

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Workers AI integration routes requests across multiple models (e.g. `@cf/meta/llama-3.1-8b-instruct` for cheap completions, `@cf/meta/llama-3.3-70b-instruct-fp8-fast` for quality-sensitive paths). Monthly billing surprises appear because neither the Cloudflare dashboard nor Workers AI's `AiTextGenerationOutput` response exposes per-request cost broken down by model, caller, or feature. You need to track token usage per model, translate it to estimated cost, persist time-series data to Analytics Engine, and alert when a feature's daily spend approaches a budget.

## Context

Workers AI charges by **neuron consumption** — a unit combining input tokens, output tokens, and model weight. Cloudflare publishes per-model neuron costs on their pricing page. The Workers AI binding returns `usage` in the response object (when streaming is disabled), giving you `prompt_tokens` and `completion_tokens`. From these you can compute estimated cost using published per-1M-token rates.

This article covers:
1. Extracting token usage from Workers AI responses.
2. Translating tokens → estimated USD cost using a rate table.
3. Writing per-request cost data to Analytics Engine, keyed by model, feature, and environment.
4. Querying for daily spend by feature and triggering a budget-breach alert.

> **Note**: Cloudflare bills neurons, not dollars-per-token directly. The rate table below is an approximation based on published pricing; treat the dollar figures as directional estimates, not exact billing values.

---

## 1. Model Cost Rate Table

```typescript
// worker/src/ai-cost.ts

/** Estimated USD per 1,000 tokens (input and output may differ by model) */
export interface ModelRate {
  inputPer1kTokens: number;
  outputPer1kTokens: number;
}

// Source: Cloudflare Workers AI pricing page (approximate, verify against current pricing)
export const MODEL_RATES: Record<string, ModelRate> = {
  "@cf/meta/llama-3.1-8b-instruct":            { inputPer1kTokens: 0.000045, outputPer1kTokens: 0.000045 },
  "@cf/meta/llama-3.3-70b-instruct-fp8-fast":  { inputPer1kTokens: 0.000120, outputPer1kTokens: 0.000120 },
  "@cf/mistral/mistral-7b-instruct-v0.1":       { inputPer1kTokens: 0.000011, outputPer1kTokens: 0.000011 },
  "@cf/google/gemma-7b-it":                     { inputPer1kTokens: 0.000015, outputPer1kTokens: 0.000015 },
  "@cf/baai/bge-large-en-v1.5":                 { inputPer1kTokens: 0.000001, outputPer1kTokens: 0.0 },
};

export function estimateCostUsd(
  model: string,
  promptTokens: number,
  completionTokens: number,
): number {
  const rate = MODEL_RATES[model];
  if (!rate) return 0; // unknown model — log separately
  return (
    (promptTokens / 1000) * rate.inputPer1kTokens +
    (completionTokens / 1000) * rate.outputPer1kTokens
  );
}
```

---

## 2. Workers AI Invocation with Cost Instrumentation

```typescript
// worker/src/index.ts

import type { Ai, AnalyticsEngineDataset } from "@cloudflare/workers-types";
import { estimateCostUsd } from "./ai-cost.js";

export interface Env {
  AI: Ai;
  COST_METRICS: AnalyticsEngineDataset;
  ENVIRONMENT: string; // "production" | "staging"
}

interface CompletionRequest {
  prompt: string;
  model?: string;
  feature?: string; // e.g. "summarise", "classify", "chat"
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") return new Response("method not allowed", { status: 405 });

    let body: CompletionRequest;
    try {
      body = await request.json() as CompletionRequest;
    } catch {
      return new Response("invalid JSON", { status: 400 });
    }

    const model = body.model ?? "@cf/meta/llama-3.1-8b-instruct";
    const feature = body.feature ?? "default";
    const t0 = Date.now();

    const response = await env.AI.run(
      model as Parameters<Ai["run"]>[0],
      {
        prompt: body.prompt,
        max_tokens: 512,
      },
    );

    const latencyMs = Date.now() - t0;

    // Workers AI returns usage when not streaming
    const usage = (response as { usage?: { prompt_tokens: number; completion_tokens: number } }).usage;
    const promptTokens = usage?.prompt_tokens ?? 0;
    const completionTokens = usage?.completion_tokens ?? 0;
    const totalTokens = promptTokens + completionTokens;
    const estimatedCostUsd = estimateCostUsd(model, promptTokens, completionTokens);

    // Structured log — tail Worker can also collect this
    console.log(JSON.stringify({
      event: "ai.inference.complete",
      model,
      feature,
      promptTokens,
      completionTokens,
      totalTokens,
      estimatedCostUsd,
      latencyMs,
      environment: env.ENVIRONMENT,
    }));

    // Write directly from the fetch Worker for lowest latency gap
    ctx.waitUntil(
      Promise.resolve(
        env.COST_METRICS.writeDataPoint({
          blobs: [
            model,                // blob1: model name
            feature,              // blob2: feature / use-case label
            env.ENVIRONMENT,      // blob3: environment
          ],
          doubles: [
            promptTokens,         // double1: prompt tokens
            completionTokens,     // double2: completion tokens
            totalTokens,          // double3: total tokens
            estimatedCostUsd,     // double4: estimated USD cost
            latencyMs,            // double5: inference latency ms
            1,                    // double6: invocation count (for SUM queries)
          ],
          indexes: [feature],     // index: filter per feature in AE SQL
        }),
      ),
    );

    const text = typeof response === "object" && response !== null && "response" in response
      ? (response as { response: string }).response
      : JSON.stringify(response);

    return Response.json({
      text,
      usage: { promptTokens, completionTokens, estimatedCostUsd },
    });
  },
};
```

---

## 3. Analytics Engine Queries for Cost Analysis

```sql
-- Daily spend by model and feature for the last 7 days
SELECT
  toDate(timestamp)       AS day,
  blob1                   AS model,
  blob2                   AS feature,
  SUM(double4)            AS estimated_cost_usd,
  SUM(double3)            AS total_tokens,
  COUNT()                 AS invocations,
  AVG(double5)            AS avg_latency_ms
FROM COST_METRICS
WHERE blob3 = 'production'
  AND timestamp > NOW() - INTERVAL '7' DAY
GROUP BY day, model, feature
ORDER BY day DESC, estimated_cost_usd DESC;

-- Cost per 1k invocations by feature (efficiency metric)
SELECT
  blob2                                     AS feature,
  SUM(double4) / (COUNT() / 1000.0)         AS cost_per_1k_invocations_usd,
  AVG(double3)                              AS avg_tokens_per_call,
  COUNT()                                   AS invocations
FROM COST_METRICS
WHERE blob3 = 'production'
  AND timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY feature
ORDER BY cost_per_1k_invocations_usd DESC;

-- Hourly cost burn rate today (use to project daily spend)
SELECT
  toStartOfHour(timestamp)  AS hour,
  SUM(double4)              AS hourly_cost_usd,
  SUM(double3)              AS hourly_tokens
FROM COST_METRICS
WHERE blob3 = 'production'
  AND toDate(timestamp) = today()
GROUP BY hour
ORDER BY hour ASC;
```

---

## 4. Budget Alert Worker

Track a per-feature daily budget and alert when 80% of it is consumed.

```typescript
// alert-worker/src/index.ts

export interface Env {
  CF_ACCOUNT_ID: string;
  AE_TOKEN: string;
  SLACK_WEBHOOK_URL: string;
  /** JSON map of feature → daily budget USD, e.g. '{"summarise":1.0,"chat":5.0}' */
  FEATURE_BUDGETS: string;
}

interface BudgetRow {
  feature: string;
  spent_today: number;
  invocations: number;
}

export default {
  async scheduled(_evt: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(checkBudgets(env));
  },
};

async function checkBudgets(env: Env): Promise<void> {
  const budgets: Record<string, number> = JSON.parse(env.FEATURE_BUDGETS ?? "{}");

  const sql = `
    SELECT
      blob2           AS feature,
      SUM(double4)    AS spent_today,
      COUNT()         AS invocations
    FROM COST_METRICS
    WHERE blob3 = 'production'
      AND toDate(timestamp) = today()
    GROUP BY feature
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.AE_TOKEN}` },
      body: sql,
    },
  );

  const json = await res.json() as { data: BudgetRow[] };
  if (!json.data?.length) return;

  const alerts: string[] = [];

  for (const row of json.data) {
    const budget = budgets[row.feature];
    if (!budget) continue;
    const pct = row.spent_today / budget;
    if (pct >= 0.8) {
      alerts.push(
        `• \`${row.feature}\`: $${row.spent_today.toFixed(4)} / $${budget.toFixed(2)} budget (${(pct * 100).toFixed(0)}%) — ${row.invocations} calls`,
      );
    }
  }

  if (!alerts.length) return;

  await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `:moneybag: *Workers AI daily budget warning*\n${alerts.join("\n")}\nAt current burn rate, budget may be exceeded before midnight UTC.`,
    }),
  });
}
```

---

## 5. Tail Worker Alternative — Collect from Structured Logs

If you prefer to centralise all Analytics Engine writes in a tail Worker rather than writing from the fetch handler:

```typescript
// tail-worker/src/index.ts

import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";

export interface Env { COST_METRICS: AnalyticsEngineDataset }

interface InferenceLog {
  event: string;
  model?: string;
  feature?: string;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  estimatedCostUsd?: number;
  latencyMs?: number;
  environment?: string;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        let parsed: InferenceLog;
        try {
          parsed = JSON.parse(typeof log.message[0] === "string"
            ? log.message[0] : JSON.stringify(log.message[0]));
        } catch { continue; }

        if (parsed.event !== "ai.inference.complete") continue;

        env.COST_METRICS.writeDataPoint({
          blobs: [parsed.model ?? "unknown", parsed.feature ?? "default", parsed.environment ?? "unknown"],
          doubles: [
            parsed.promptTokens ?? 0,
            parsed.completionTokens ?? 0,
            parsed.totalTokens ?? 0,
            parsed.estimatedCostUsd ?? 0,
            parsed.latencyMs ?? 0,
            1,
          ],
          indexes: [parsed.feature ?? "default"],
        });
      }
    }
  },
};
```

Remove the direct `writeDataPoint` from the fetch Worker when using this approach to avoid double-counting.

---

## Anti-patterns

- **Computing cost inside the tail Worker using a hardcoded rate table** — the tail Worker processes events asynchronously; if you update the rate table without redeploying the tail Worker, historical data becomes inconsistent. Keep the cost estimate in the fetch Worker or recompute it at query time in AE SQL.
- **Streaming inference and expecting `usage` in the response** — the `usage` object is only present in non-streaming `AiTextGenerationOutput`; streaming responses do not return token counts. Accumulate stream chunks if you need token estimates for streaming paths.
- **Using `double4` (estimated cost) as exact billing input** — the neuron model and your per-token approximation will diverge from the actual bill; label all dashboard values as "estimated" and reconcile monthly against the Cloudflare invoice.
- **Treating all invocations as equal** — a 4096-token completion costs vastly more than a 32-token embedding; never aggregate cost by invocation count without also reporting average tokens per call.

## Gotchas

- `env.AI.run()` may throw on model overload or quota breach; always wrap in try/catch and emit an error log with the model name so you can detect model-specific failure rates.
- Workers AI token counts are approximate — the tokeniser varies by model family. A 1000-character English prompt typically encodes to 200–300 tokens depending on the model.
- Analytics Engine `writeDataPoint` is silently dropped if you exceed the **25 blobs + 25 doubles + 1 index** limit per data point; the schema above uses 3 blobs and 6 doubles, well within limits.
- `ctx.waitUntil` must be called synchronously within the `fetch` handler scope; if you await the AI call and then call `ctx.waitUntil`, verify the context is still active (it will be, unless the request already returned a response and the runtime settled).

## Verification

```bash
# 1. Deploy
wrangler deploy

# 2. Fire a test inference
curl -s -X POST https://my-worker.example.workers.dev/ \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Summarise the Cloudflare Workers platform in one sentence.","feature":"summarise"}' | jq .usage

# 3. Confirm token counts and estimatedCostUsd are non-zero in the response

# 4. After ~90 s query Analytics Engine
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $AE_TOKEN" \
  --data "SELECT blob1, SUM(double4) AS cost, SUM(double3) AS tokens FROM COST_METRICS WHERE timestamp > NOW() - INTERVAL '5' MINUTE GROUP BY blob1"

# 5. Confirm the model appears with non-zero cost and token counts
```

## Related

- `workers-ai-token-usage-budget-analytics-engine.md`
- `workers-ai-inference-latency-analytics-engine.md`
- `workers-ai-anomaly-detection-analytics-engine.md`
- `cloudflare-billing-cost-anomaly-detection.md`
- `analytics-engine-multi-tenant-usage-metering.md`

## Sources

- Cloudflare Workers AI Pricing — developers.cloudflare.com/workers-ai/platform/pricing
- Cloudflare Workers AI Models — developers.cloudflare.com/workers-ai/models
- Cloudflare Analytics Engine — developers.cloudflare.com/analytics/analytics-engine
- Workers AI AiTextGenerationOutput type — developers.cloudflare.com/workers-ai/configuration/bindings
