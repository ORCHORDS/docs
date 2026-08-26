# AI Gateway Cost Attribution Per-Tenant with D1

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

You operate a multi-tenant SaaS product that proxies AI inference through Cloudflare AI Gateway. At the end of the month you cannot tell which tenant consumed what — the gateway bill is a single line item. You need per-tenant token and cost tracking with enough granularity to bill customers, enforce quotas, and spot runaway consumers before they blow the budget.

## Context

Cloudflare AI Gateway returns token-usage metadata in the response body (`usage.prompt_tokens`, `usage.completion_tokens`) for OpenAI-compatible providers and in Workers AI binding responses. A proxy Worker intercepts every inference call, extracts the usage fields from the JSON response, and writes a row to a D1 table that acts as the ledger. D1's SQL interface makes it straightforward to aggregate by tenant, model, and time window. Rate-limiting and quota enforcement are layered on top of the same ledger table.

Model cost coefficients are stored in a separate D1 table so they can be updated without redeploying the Worker.

---

## 1. D1 Schema

```sql
-- Run once with: wrangler d1 execute ai-cost-db --file=schema.sql

CREATE TABLE IF NOT EXISTS inference_usage (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id   TEXT    NOT NULL,
  model       TEXT    NOT NULL,
  provider    TEXT    NOT NULL,
  prompt_tokens     INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens      INTEGER NOT NULL DEFAULT 0,
  cost_usd_micro    INTEGER NOT NULL DEFAULT 0,  -- cost in micro-dollars (1e-6 USD)
  status_code       INTEGER NOT NULL,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_usage_tenant ON inference_usage(tenant_id, created_at);
CREATE INDEX idx_usage_model  ON inference_usage(model, created_at);

CREATE TABLE IF NOT EXISTS model_pricing (
  model             TEXT PRIMARY KEY,
  prompt_usd_per_1k REAL NOT NULL,   -- USD per 1k prompt tokens
  compl_usd_per_1k  REAL NOT NULL    -- USD per 1k completion tokens
);

-- Seed example pricing (update to reflect current provider rates)
INSERT OR REPLACE INTO model_pricing VALUES
  ('@cf/meta/llama-3.1-8b-instruct',  0.0,    0.0),    -- included in Workers AI plan
  ('@cf/mistral/mistral-7b-instruct',  0.0,    0.0),
  ('gpt-4o',                           0.005,  0.015),
  ('gpt-4o-mini',                      0.00015, 0.0006),
  ('claude-sonnet-4-5',                0.003,  0.015);
```

---

## 2. Proxy Worker

The Worker sits in front of the AI Gateway universal endpoint. It buffers the response body (non-streaming path) to extract usage, then persists the row to D1 asynchronously.

```typescript
// src/cost-attribution-proxy.ts
export interface Env {
  AI_GATEWAY_URL: string;
  AI_GATEWAY_TOKEN: string;
  DB: D1Database;
}

interface UsagePayload {
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens?: number };
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const tenantId = request.headers.get('x-tenant-id') ?? 'unknown';
    const url = new URL(request.url);
    // Convention: /v1/{provider}/{...rest}
    const [, , provider, ...rest] = url.pathname.split('/');
    const model = await extractModel(request.clone());

    const gatewayTarget = `${env.AI_GATEWAY_URL}/${provider}/${rest.join('/')}`;
    const upstreamResponse = await fetch(new Request(gatewayTarget, {
      method: request.method,
      headers: { ...Object.fromEntries(request.headers), Authorization: `Bearer ${env.AI_GATEWAY_TOKEN}` },
      body: request.body,
    }));

    const statusCode = upstreamResponse.status;

    // Clone to read body without consuming the stream returned to the client
    const responseForClient = upstreamResponse.clone();
    ctx.waitUntil(
      recordUsage(env.DB, upstreamResponse, tenantId, model, provider ?? 'unknown', statusCode)
    );

    return responseForClient;
  },
};

async function extractModel(req: Request): Promise<string> {
  try {
    const body = await req.json() as { model?: string };
    return body.model ?? 'unknown';
  } catch {
    return 'unknown';
  }
}

async function recordUsage(
  db: D1Database,
  response: Response,
  tenantId: string,
  model: string,
  provider: string,
  statusCode: number
): Promise<void> {
  let promptTokens = 0;
  let completionTokens = 0;

  if (statusCode === 200) {
    try {
      const body = await response.json() as UsagePayload;
      promptTokens = body.usage?.prompt_tokens ?? 0;
      completionTokens = body.usage?.completion_tokens ?? 0;
    } catch {
      // Non-JSON or streaming — tokens unknown
    }
  }

  const totalTokens = promptTokens + completionTokens;

  // Fetch cost coefficients
  const pricing = await db
    .prepare('SELECT prompt_usd_per_1k, compl_usd_per_1k FROM model_pricing WHERE model = ?')
    .bind(model)
    .first<{ prompt_usd_per_1k: number; compl_usd_per_1k: number }>();

  const costMicro = pricing
    ? Math.round(
        (promptTokens / 1000) * pricing.prompt_usd_per_1k * 1_000_000 +
        (completionTokens / 1000) * pricing.compl_usd_per_1k * 1_000_000
      )
    : 0;

  await db
    .prepare(`
      INSERT INTO inference_usage
        (tenant_id, model, provider, prompt_tokens, completion_tokens, total_tokens, cost_usd_micro, status_code)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `)
    .bind(tenantId, model, provider, promptTokens, completionTokens, totalTokens, costMicro, statusCode)
    .run();
}
```

---

## 3. Quota Enforcement Middleware

Check the rolling 24-hour token total before forwarding. Return 429 if the tenant is over quota.

```typescript
// src/quota-check.ts
export async function enforceQuota(
  db: D1Database,
  tenantId: string,
  dailyTokenLimit: number
): Promise<{ allowed: boolean; used: number }> {
  const result = await db
    .prepare(`
      SELECT COALESCE(SUM(total_tokens), 0) AS used
      FROM inference_usage
      WHERE tenant_id = ?
        AND created_at >= datetime('now', '-1 day')
    `)
    .bind(tenantId)
    .first<{ used: number }>();

  const used = result?.used ?? 0;
  return { allowed: used < dailyTokenLimit, used };
}
```

In the main Worker, call this before proxying:

```typescript
const { allowed, used } = await enforceQuota(env.DB, tenantId, 500_000);
if (!allowed) {
  return new Response(
    JSON.stringify({ error: 'token_quota_exceeded', used }),
    { status: 429, headers: { 'Content-Type': 'application/json' } }
  );
}
```

---

## 4. Cost Reporting Queries

```sql
-- Monthly cost by tenant (current calendar month)
SELECT
  tenant_id,
  SUM(prompt_tokens)     AS prompt_tokens,
  SUM(completion_tokens) AS completion_tokens,
  ROUND(SUM(cost_usd_micro) / 1e6, 4) AS cost_usd
FROM inference_usage
WHERE created_at >= date('now', 'start of month')
GROUP BY tenant_id
ORDER BY cost_usd DESC;

-- Daily spend trend for a specific tenant
SELECT
  date(created_at)                        AS day,
  SUM(total_tokens)                        AS tokens,
  ROUND(SUM(cost_usd_micro) / 1e6, 4)     AS cost_usd
FROM inference_usage
WHERE tenant_id = 'acme-corp'
  AND created_at >= datetime('now', '-30 days')
GROUP BY day
ORDER BY day;

-- Top 5 models by cost across all tenants
SELECT
  model,
  ROUND(SUM(cost_usd_micro) / 1e6, 4) AS cost_usd,
  SUM(total_tokens) AS tokens
FROM inference_usage
WHERE created_at >= date('now', 'start of month')
GROUP BY model
ORDER BY cost_usd DESC
LIMIT 5;
```

---

## 5. Automated Monthly Report Worker

```typescript
// src/monthly-report.ts  — cron: "0 0 1 * *" (1st of each month, midnight UTC)
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const rows = await env.DB
      .prepare(`
        SELECT tenant_id, ROUND(SUM(cost_usd_micro) / 1e6, 4) AS cost_usd, SUM(total_tokens) AS tokens
        FROM inference_usage
        WHERE created_at >= datetime('now', 'start of month', '-1 month')
          AND created_at <  datetime('now', 'start of month')
        GROUP BY tenant_id
        ORDER BY cost_usd DESC
      `)
      .all<{ tenant_id: string; cost_usd: number; tokens: number }>();

    await fetch(env.REPORT_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: 'monthly_ai_cost', data: rows.results }),
    });
  },
};
```

---

## Anti-patterns

- **Storing cost_usd as REAL** — floating-point rounding errors accumulate across millions of rows. Store micro-dollars as INTEGER and convert only at display time.
- **Blocking the response on D1 writes** — always wrap ledger writes in `ctx.waitUntil()` so database latency is invisible to the caller.
- **Hard-coding pricing in Worker code** — keep coefficients in the `model_pricing` D1 table so rate changes require a SQL UPDATE, not a deployment.
- **Tracking only successful requests** — record all status codes; failed calls may still consume quota on some providers.
- **Reading the response body synchronously** — clone the response first (`upstreamResponse.clone()`) before consuming the body; otherwise the original stream is exhausted before it reaches the client.

## Gotchas

- Streaming responses (`stream: true`) do not expose `usage` in the initial chunks on most providers. Either wait for the final `[DONE]` chunk (which may contain usage) or count tokens client-side with a tokenizer library.
- D1 has a 10 ms CPU limit per query on the free tier; complex aggregations over large tables may need pagination or offloading to an Analytics Engine rollup.
- `datetime('now', 'start of month')` is SQLite-specific syntax — it works in D1 but not in standard SQL dialects.
- The proxy must be deployed as a `fetch` handler Worker, not as a Service Binding passthrough, to have access to the raw response body.
- Workers AI binding calls (via `env.AI`) do not pass through AI Gateway unless you explicitly route them through the gateway URL — use the REST approach if you need unified logging.

## Verification

1. Send 5 requests with different `x-tenant-id` headers and confirm rows appear in `inference_usage` via `wrangler d1 execute ai-cost-db --command "SELECT * FROM inference_usage ORDER BY id DESC LIMIT 10"`.
2. Set `daily_token_limit` to 1 token for a test tenant and verify the next request returns HTTP 429.
3. Run the monthly report query manually for the current month and confirm `cost_usd` matches expected values from the `model_pricing` table.
4. Verify `cost_usd_micro` is stored as integer: `SELECT typeof(cost_usd_micro) FROM inference_usage LIMIT 1` → `integer`.

## Related

- `ai-gateway-budget-caps-spend-control.md`
- `ai-gateway-rate-limiting.md`
- `vectorize-multi-tenant-namespace-partitioning.md`
- `retrieval-augmented-generation-d1-vectorize.md`
- `llm-cost-optimization.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/ai-gateway/reference/workers-binding/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
