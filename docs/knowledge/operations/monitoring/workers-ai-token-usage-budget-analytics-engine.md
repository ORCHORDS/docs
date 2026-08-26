# Workers AI Token Usage Budget Tracking with Analytics Engine

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Workers AI token consumption accumulates across dozens of scripts and model variants with no centralised visibility, causing unexpected billing spikes and quota exhaustion at month-end. You need per-model, per-tenant token counters retained over 30 days so you can enforce per-user budgets, project monthly spend, and alert before quota is exhausted.

## Context

Workers AI responses include a `usage` object on supported models that contains `prompt_tokens`, `completion_tokens`, and `total_tokens`. These fields are written to Analytics Engine as double values keyed by model name and a tenant or feature label. A cron Worker queries the SQL API daily to compare cumulative totals against configured budgets and sends alerts when teams approach their limits. This approach works without an external billing API and survives plan changes transparently.

## 1. Token-Aware AI Call Wrapper

```typescript
// src/ai-token-tracker.ts
export interface Env {
  AI: Ai;
  TOKEN_USAGE: AnalyticsEngineDataset;
}

export interface UsageSummary {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

interface AiResponseWithUsage {
  response?: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export async function trackedTextGeneration(
  env: Env,
  model: string,
  prompt: string,
  tenant: string
): Promise<{ text: string; usage: UsageSummary }> {
  const result = await env.AI.run(
    model as Parameters<Ai["run"]>[0],
    { prompt } as any
  ) as AiResponseWithUsage;

  const usage: UsageSummary = {
    promptTokens: result.usage?.prompt_tokens ?? estimateTokens(prompt),
    completionTokens: result.usage?.completion_tokens ?? 0,
    totalTokens:
      result.usage?.total_tokens ??
      (result.usage?.prompt_tokens ?? estimateTokens(prompt)) +
        (result.usage?.completion_tokens ?? 0),
  };

  env.TOKEN_USAGE.writeDataPoint({
    blobs: [model, tenant, "text-generation"],
    doubles: [
      usage.promptTokens,
      usage.completionTokens,
      usage.totalTokens,
      1, // request count
    ],
    indexes: [model],
  });

  return { text: result.response ?? "", usage };
}

export async function trackedEmbedding(
  env: Env,
  model: string,
  text: string,
  tenant: string
): Promise<{ data: number[][]; usage: UsageSummary }> {
  const result = await env.AI.run(
    model as Parameters<Ai["run"]>[0],
    { text: [text] } as any
  ) as { data: number[][]; usage?: AiResponseWithUsage["usage"] };

  const promptTokens = result.usage?.prompt_tokens ?? estimateTokens(text);

  env.TOKEN_USAGE.writeDataPoint({
    blobs: [model, tenant, "embedding"],
    doubles: [
      promptTokens,
      0, // embeddings have no completion tokens
      promptTokens,
      1,
    ],
    indexes: [model],
  });

  return {
    data: result.data,
    usage: { promptTokens, completionTokens: 0, totalTokens: promptTokens },
  };
}

/** Rough 4-chars-per-token estimate when the API does not return usage. */
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}
```

## 2. wrangler.toml Binding

```toml
name = "my-ai-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"

[[analytics_engine_datasets]]
binding = "TOKEN_USAGE"
dataset = "workers_ai_token_usage"
```

## 3. Request Handler with Tenant Extraction

```typescript
// src/index.ts
import { trackedTextGeneration, type Env } from "./ai-token-tracker";

interface RequestEnv extends Env {
  TENANT_HEADER: string; // e.g. "x-tenant-id"
}

export default {
  async fetch(request: Request, env: RequestEnv): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const tenant =
      request.headers.get("x-tenant-id") ??
      request.headers.get("cf-connecting-ip") ??
      "unknown";

    const { prompt, model = "@cf/meta/llama-3.1-8b-instruct" } =
      await request.json<{ prompt: string; model?: string }>();

    const { text, usage } = await trackedTextGeneration(
      env,
      model,
      prompt,
      tenant
    );

    return Response.json({
      text,
      usage: {
        prompt_tokens: usage.promptTokens,
        completion_tokens: usage.completionTokens,
        total_tokens: usage.totalTokens,
      },
    });
  },
} satisfies ExportedHandler<RequestEnv>;
```

## 4. Cumulative Token Budget Query

```typescript
// src/budget-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export interface TokenBudgetRow {
  model: string;
  tenant: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  request_count: number;
}

export async function fetchTokenUsage(
  intervalDays = 30
): Promise<TokenBudgetRow[]> {
  const sql = `
    SELECT
      blob1  AS model,
      blob2  AS tenant,
      sum(double1) AS prompt_tokens,
      sum(double2) AS completion_tokens,
      sum(double3) AS total_tokens,
      sum(double4) AS request_count
    FROM workers_ai_token_usage
    WHERE timestamp > now() - INTERVAL '${intervalDays}' DAY
    GROUP BY model, tenant
    ORDER BY total_tokens DESC
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

  if (!resp.ok) throw new Error(`SQL API error: ${resp.status}`);
  const json = (await resp.json()) as { data: TokenBudgetRow[] };
  return json.data ?? [];
}
```

## 5. Budget Enforcement and Alert Cron

```typescript
// src/budget-alert.ts
import { fetchTokenUsage } from "./budget-query";

// Monthly token budgets per tenant (total tokens across all models)
const TENANT_BUDGETS: Record<string, number> = {
  "tenant-alpha": 5_000_000,
  "tenant-beta": 2_000_000,
  "tenant-gamma": 500_000,
  default: 100_000,
};

// Per-model budgets (shared across all tenants) to catch runaway scripts
const MODEL_BUDGETS: Record<string, number> = {
  "@cf/meta/llama-3.1-70b-instruct": 10_000_000,
  "@cf/meta/llama-3.1-8b-instruct": 50_000_000,
  "@cf/baai/bge-base-en-v1.5": 100_000_000,
};

export async function checkTokenBudgets(webhookUrl: string): Promise<void> {
  const rows = await fetchTokenUsage(30);
  const alerts: string[] = [];

  // Aggregate per tenant
  const tenantTotals = new Map<string, number>();
  for (const row of rows) {
    tenantTotals.set(
      row.tenant,
      (tenantTotals.get(row.tenant) ?? 0) + row.total_tokens
    );
  }

  for (const [tenant, used] of tenantTotals) {
    const budget = TENANT_BUDGETS[tenant] ?? TENANT_BUDGETS.default;
    const pct = (used / budget) * 100;
    if (pct >= 80) {
      alerts.push(
        `Tenant \`${tenant}\`: ${used.toLocaleString()} / ${budget.toLocaleString()} tokens (${pct.toFixed(1)}%)`
      );
    }
  }

  // Aggregate per model
  const modelTotals = new Map<string, number>();
  for (const row of rows) {
    modelTotals.set(
      row.model,
      (modelTotals.get(row.model) ?? 0) + row.total_tokens
    );
  }

  for (const [model, used] of modelTotals) {
    const budget = MODEL_BUDGETS[model];
    if (budget !== undefined) {
      const pct = (used / budget) * 100;
      if (pct >= 90) {
        alerts.push(
          `Model \`${model}\`: ${used.toLocaleString()} / ${budget.toLocaleString()} tokens (${pct.toFixed(1)}%)`
        );
      }
    }
  }

  if (alerts.length === 0) return;

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `Workers AI token budget warning:\n${alerts.join("\n")}`,
    }),
  });
}

// wrangler.toml cron entry:
// [triggers]
// crons = ["0 9 * * *"]   # daily at 09:00 UTC
```

## 6. Daily Token Trend Query

```sql
SELECT
  toStartOfInterval(timestamp, INTERVAL '1' DAY) AS day,
  blob1  AS model,
  blob2  AS tenant,
  sum(double3) AS total_tokens,
  sum(double4) AS requests
FROM workers_ai_token_usage
WHERE timestamp > now() - INTERVAL '30' DAY
GROUP BY day, model, tenant
ORDER BY day ASC, total_tokens DESC
```

## Anti-patterns

- **Trusting only `total_tokens` without separating prompt and completion tokens**: completion tokens cost significantly more per unit than prompt tokens on some models; track them separately to project costs accurately.
- **Using IP address as the tenant label in shared infrastructure**: IP addresses rotate in CDN environments; use an authenticated user ID or API key hash instead.
- **Estimating tokens on every call**: estimation via character count is a 15-30% undercount for code and structured data; prefer the API's `usage` field and fall back to estimation only when the field is absent.
- **Setting a single global budget without per-model breakdown**: a tenant that switches from a small model to a 70B parameter model can exhaust the same token budget 10x faster.
- **Writing model name with version qualifiers that change over time**: if Cloudflare renames a model alias, historical and current data aggregate under different keys; use the canonical model path from the Workers AI docs.

## Gotchas

- Not all Workers AI models return a `usage` object; the Llama family and embedding models do, but image generation and speech models may not — always check `result.usage` for undefined before reading token counts.
- Analytics Engine doubles are IEEE 754 float64; token counts up to ~9 quadrillion are representable exactly, so there is no precision loss for realistic usage figures.
- The Analytics Engine SQL API enforces a 6-hour query window by default for free-tier accounts; rolling 30-day budget queries require a paid plan with the extended retention window.
- Workers AI `usage.total_tokens` occasionally differs from `prompt_tokens + completion_tokens` by 1 due to rounding; use `total_tokens` as the authoritative billing figure.

## Verification

1. Deploy the Worker and send 10 test prompts with varied lengths.
2. After 2 minutes, query the SQL API for the last hour; confirm rows exist with non-zero `prompt_tokens` and `total_tokens`.
3. Manually set a tenant budget to `1` in `TENANT_BUDGETS` and run the cron handler; confirm the webhook fires.
4. Restore the budget, run the cron again, and confirm no alert fires.
5. Test the embedding path separately with the `trackedEmbedding` function and confirm `completion_tokens = 0` in the stored rows.

## Related

- `workers-ai-inference-latency-analytics-engine.md`
- `workers-ai-anomaly-detection-analytics-engine.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `observability-cost-control.md`

## Sources

- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
