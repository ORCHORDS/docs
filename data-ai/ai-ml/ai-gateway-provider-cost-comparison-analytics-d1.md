# AI Gateway Provider Cost Comparison Analytics D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project routes anonymous posts through multiple AI providers (Anthropic Claude for moderation, Workers AI for embeddings, OpenAI GPT-4o for fallback classification). Finance asks for a weekly breakdown: which provider is cheapest per inference task, what the blended cost-per-1k-tokens is across the platform, and whether the current routing logic actually saves money versus a single-provider approach. The data lives in AI Gateway logs but requires structured aggregation to answer these questions.

---

## Context

AI Gateway emits per-request logs containing provider name, model, prompt tokens, completion tokens, and response latency. By forwarding these to D1 via a log-drain Worker, you build a queryable cost ledger. Each provider publishes its own token pricing; the Worker looks up rates from a KV config, computes USD cost, and inserts a row. SQL GROUP BY queries then produce the comparison reports finance needs.

Key constraints:
- AI Gateway log webhooks fire asynchronously; the drain Worker must be idempotent on duplicate delivery.
- Token counts for Workers AI models are in the gateway response headers, not the body.
- Provider pricing changes; rates must be runtime-configurable, not hardcoded.
- D1 row limits: aim for one row per request, not one per token.

---

## Schema Design

```sql
-- migrations/0012_provider_cost_ledger.sql
CREATE TABLE IF NOT EXISTS provider_cost_ledger (
  id            TEXT PRIMARY KEY,          -- gateway request_id (idempotency key)
  ts            INTEGER NOT NULL,          -- unix epoch ms
  provider      TEXT NOT NULL,             -- 'anthropic' | 'openai' | 'workers-ai'
  model         TEXT NOT NULL,
  task_type     TEXT NOT NULL,             -- 'moderation' | 'embedding' | 'classification'
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens  INTEGER NOT NULL DEFAULT 0,
  latency_ms    INTEGER NOT NULL DEFAULT 0,
  cost_usd_micro INTEGER NOT NULL DEFAULT 0, -- cost in micro-dollars (1e-6 USD) avoids float
  status_code   INTEGER NOT NULL DEFAULT 200,
  example project_env      TEXT NOT NULL DEFAULT 'prod'
);

CREATE INDEX idx_pcl_ts       ON provider_cost_ledger(ts);
CREATE INDEX idx_pcl_provider ON provider_cost_ledger(provider, ts);
CREATE INDEX idx_pcl_task     ON provider_cost_ledger(task_type, ts);
```

---

## KV Pricing Config

```typescript
// src/lib/pricing.ts
export interface ProviderRate {
  inputPer1kTokens:  number; // USD
  outputPer1kTokens: number; // USD
}

// Rates stored in KV as JSON, keyed by "rate:<provider>:<model>"
// e.g. "rate:anthropic:claude-3-5-haiku-20241022"
export async function getRate(
  kv: KVNamespace,
  provider: string,
  model: string
): Promise<ProviderRate> {
  const key = `rate:${provider}:${model}`;
  const cached = await kv.get<ProviderRate>(key, 'json');
  if (cached) return cached;

  // Hard fallback so the drain never silently drops rows
  const defaults: Record<string, ProviderRate> = {
    'anthropic:claude-3-5-haiku-20241022': { inputPer1kTokens: 0.0008, outputPer1kTokens: 0.004 },
    'openai:gpt-4o-mini':                  { inputPer1kTokens: 0.00015, outputPer1kTokens: 0.0006 },
    'workers-ai:@cf/baai/bge-large-en-v1.5': { inputPer1kTokens: 0.00002, outputPer1kTokens: 0 },
    'workers-ai:@cf/meta/llama-3.1-8b-instruct': { inputPer1kTokens: 0.00011, outputPer1kTokens: 0.00011 },
  };

  return defaults[`${provider}:${model}`] ?? { inputPer1kTokens: 0, outputPer1kTokens: 0 };
}

export function computeCostMicro(
  rate: ProviderRate,
  promptTokens: number,
  completionTokens: number
): number {
  const inputCost  = (promptTokens / 1000) * rate.inputPer1kTokens;
  const outputCost = (completionTokens / 1000) * rate.outputPer1kTokens;
  return Math.round((inputCost + outputCost) * 1_000_000); // micro-dollars
}
```

---

## Log-Drain Worker

```typescript
// src/workers/gateway-log-drain.ts
import { getRate, computeCostMicro } from '../lib/pricing';

export interface Env {
  DB: D1Database;
  PRICING_KV: KVNamespace;
  DRAIN_SECRET: string; // shared secret from AI Gateway webhook config
}

interface GatewayLogEvent {
  id: string;
  timestamp: number; // ms
  provider: string;
  model: string;
  request: { metadata?: { task_type?: string; example project_env?: string } };
  response: {
    status: number;
    latency: number; // ms
    usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  };
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Verify shared secret
    const auth = req.headers.get('X-Gateway-Secret');
    if (auth !== env.DRAIN_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    let events: GatewayLogEvent[];
    try {
      events = await req.json();
    } catch {
      return new Response('Bad JSON', { status: 400 });
    }

    // AI Gateway may batch multiple events per webhook call
    const rows = await Promise.all(
      events.map(async (evt) => {
        const usage = evt.response.usage ?? { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
        const rate  = await getRate(env.PRICING_KV, evt.provider, evt.model);
        const cost  = computeCostMicro(rate, usage.prompt_tokens, usage.completion_tokens);

        return {
          id:                evt.id,
          ts:                evt.timestamp,
          provider:          evt.provider,
          model:             evt.model,
          task_type:         evt.request.metadata?.task_type ?? 'unknown',
          prompt_tokens:     usage.prompt_tokens,
          completion_tokens: usage.completion_tokens,
          total_tokens:      usage.total_tokens,
          latency_ms:        evt.response.latency,
          cost_usd_micro:    cost,
          status_code:       evt.response.status,
          example project_env:          evt.request.metadata?.example project_env ?? 'prod',
        };
      })
    );

    // Batch insert with ON CONFLICT IGNORE for idempotency
    const placeholders = rows.map(() =>
      '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
    ).join(', ');

    const values = rows.flatMap((r) => [
      r.id, r.ts, r.provider, r.model, r.task_type,
      r.prompt_tokens, r.completion_tokens, r.total_tokens,
      r.latency_ms, r.cost_usd_micro, r.status_code, r.example project_env,
    ]);

    await env.DB.prepare(
      `INSERT OR IGNORE INTO provider_cost_ledger
         (id, ts, provider, model, task_type, prompt_tokens, completion_tokens,
          total_tokens, latency_ms, cost_usd_micro, status_code, example project_env)
       VALUES ${placeholders}`
    ).bind(...values).run();

    return new Response('OK', { status: 200 });
  },
};
```

---

## Analytics Queries

```typescript
// src/lib/cost-analytics.ts
export async function weeklyProviderComparison(
  db: D1Database,
  daysBack = 7
): Promise<D1Result> {
  const cutoff = Date.now() - daysBack * 86_400_000;
  return db.prepare(`
    SELECT
      provider,
      task_type,
      COUNT(*)                                   AS requests,
      SUM(total_tokens)                          AS total_tokens,
      SUM(cost_usd_micro) / 1000000.0            AS cost_usd,
      AVG(latency_ms)                            AS avg_latency_ms,
      -- cost per 1k tokens in USD
      (SUM(cost_usd_micro) / 1000000.0)
        / NULLIF(SUM(total_tokens) / 1000.0, 0) AS cost_per_1k_usd,
      SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count
    FROM provider_cost_ledger
    WHERE ts >= ? AND example project_env = 'prod'
    GROUP BY provider, task_type
    ORDER BY cost_usd DESC
  `).bind(cutoff).all();
}

export async function dailyCostTrend(
  db: D1Database,
  provider: string,
  daysBack = 30
): Promise<D1Result> {
  const cutoff = Date.now() - daysBack * 86_400_000;
  return db.prepare(`
    SELECT
      DATE(ts / 1000, 'unixepoch')  AS day,
      SUM(cost_usd_micro) / 1000000.0 AS cost_usd,
      COUNT(*)                        AS requests
    FROM provider_cost_ledger
    WHERE ts >= ? AND provider = ? AND example project_env = 'prod'
    GROUP BY day
    ORDER BY day
  `).bind(cutoff, provider).all();
}

export async function modelRankingByEfficiency(
  db: D1Database,
  taskType: string
): Promise<D1Result> {
  // Lower cost_per_1k AND lower latency = more efficient
  return db.prepare(`
    SELECT
      provider,
      model,
      COUNT(*)                                   AS requests,
      AVG(latency_ms)                            AS avg_latency_ms,
      (SUM(cost_usd_micro) / 1000000.0)
        / NULLIF(SUM(total_tokens) / 1000.0, 0) AS cost_per_1k_usd,
      -- efficiency score: lower is better (normalize to range)
      (AVG(latency_ms) / 1000.0)
        + ((SUM(cost_usd_micro) / 1000000.0) / NULLIF(SUM(total_tokens) / 1000.0, 0)) * 100
                                                 AS efficiency_score
    FROM provider_cost_ledger
    WHERE task_type = ? AND status_code < 400 AND example project_env = 'prod'
    GROUP BY provider, model
    HAVING requests >= 100
    ORDER BY efficiency_score ASC
  `).bind(taskType).all();
}
```

---

## Scheduled Weekly Report

```typescript
// src/workers/weekly-cost-report.ts
import { weeklyProviderComparison, modelRankingByEfficiency } from '../lib/cost-analytics';

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const comparison = await weeklyProviderComparison(env.DB);
    const moderationRanking = await modelRankingByEfficiency(env.DB, 'moderation');

    const totalCost = (comparison.results as any[])
      .reduce((sum, r) => sum + (r.cost_usd as number), 0);

    const report = {
      week_ending:         new Date().toISOString().slice(0, 10),
      total_cost_usd:      totalCost.toFixed(4),
      by_provider_task:    comparison.results,
      moderation_ranking:  moderationRanking.results,
    };

    // Store in D1 for the dashboard Worker to read
    await env.DB.prepare(
      `INSERT INTO weekly_cost_reports (ts, report_json)
       VALUES (?, ?)`
    ).bind(Date.now(), JSON.stringify(report)).run();
  },
};
```

---

## Anti-patterns

- **Float arithmetic for money**: Never store `cost_usd REAL`. Use integer micro-dollars to avoid IEEE 754 rounding errors when aggregating millions of rows.
- **Hardcoded pricing**: Rates change monthly. Storing them in KV means a zero-deploy update; hardcoding means a re-deploy every time a provider adjusts pricing.
- **Aggregating in the drain Worker**: Keep the drain Writer thin. Do analytics in scheduled Workers or on-demand queries so the hot path never blocks on heavy SQL.
- **Ignoring error rows**: Including rows with `status_code >= 400` in cost averages skews efficiency scores downward. Filter them in ranking queries with `HAVING` clauses.
- **Per-token rows**: One row per request, not per token. D1 row count limits matter at scale; token counts are just columns.

---

## Gotchas

- Workers AI does not return token counts in the same response shape as OpenAI. The `usage` field is present in the AI Gateway log payload but may be `null` for streaming requests — default to 0 and flag for manual review.
- AI Gateway webhook delivery is at-least-once. The `INSERT OR IGNORE` on the `id` primary key is essential; without it the ledger double-counts costs.
- D1 `DATE()` function with `'unixepoch'` modifier expects seconds, not milliseconds. Divide `ts` by 1000 or store as seconds from the start.
- Provider names in AI Gateway logs use lowercase slugs (`anthropic`, `openai`, `workers-ai`); ensure KV keys match exactly.
- Cost per 1k tokens is meaningless for embedding models that produce no completion tokens. Use `inputPer1kTokens` only and set `outputPer1kTokens: 0` in the KV config.

---

## Verification

```bash
# 1. Insert a test row manually
npx wrangler d1 execute example project_DB --command="
  INSERT OR IGNORE INTO provider_cost_ledger
    (id, ts, provider, model, task_type, prompt_tokens, completion_tokens,
     total_tokens, latency_ms, cost_usd_micro, status_code, example project_env)
  VALUES
    ('test-001', unixepoch('now') * 1000, 'anthropic',
     'claude-3-5-haiku-20241022', 'moderation', 500, 50, 550, 320, 448, 200, 'prod')
"

# 2. Verify the weekly comparison returns the row
npx wrangler d1 execute example project_DB --command="
  SELECT provider, task_type, cost_per_1k_usd
  FROM (
    SELECT provider, task_type,
      (SUM(cost_usd_micro)/1000000.0) / NULLIF(SUM(total_tokens)/1000.0,0) AS cost_per_1k_usd
    FROM provider_cost_ledger
    WHERE example project_env='prod'
    GROUP BY provider, task_type
  )
"

# 3. Confirm idempotency: insert same id again, count should stay at 1
npx wrangler d1 execute example project_DB --command="
  INSERT OR IGNORE INTO provider_cost_ledger
    (id, ts, provider, model, task_type, prompt_tokens, completion_tokens,
     total_tokens, latency_ms, cost_usd_micro, status_code, example project_env)
  VALUES
    ('test-001', unixepoch('now') * 1000, 'anthropic',
     'claude-3-5-haiku-20241022', 'moderation', 999, 999, 1998, 999, 9999, 200, 'prod');
  SELECT COUNT(*) AS row_count FROM provider_cost_ledger WHERE id='test-001'
"
# Expected: row_count = 1
```

---

## Related

- `ai-gateway-cost-attribution-per-tenant-d1.md` — per-tenant cost attribution (different axis from provider comparison)
- `ai-gateway-latency-slo-analytics-engine.md` — latency SLO tracking via Analytics Engine
- `ai-gateway-rate-limiting-per-model-tier-kv.md` — rate limiting that interacts with cost budgets
- `workers-ai-model-benchmarking-latency-profiling.md` — latency benchmarking complement to cost data
- `llm-cost-optimization.md` — general strategies informed by this comparison data

---

## Sources

- Cloudflare AI Gateway log webhook docs: https://developers.cloudflare.com/ai-gateway/observability/logging/
- D1 SQL reference (DATE functions): https://developers.cloudflare.com/d1/sql-api/
- Anthropic Claude pricing: https://www.anthropic.com/pricing
- OpenAI pricing: https://openai.com/api/pricing
- Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
