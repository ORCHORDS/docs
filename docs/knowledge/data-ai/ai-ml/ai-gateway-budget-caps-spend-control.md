# AI Gateway Budget Caps and Spend Control

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
An AI-powered feature ships and a traffic spike — or a runaway retry loop — blows through the monthly LLM budget in hours. You need hard spending ceilings enforced at the gateway layer before requests ever reach the upstream provider.

## Context
Cloudflare AI Gateway sits between your Workers and upstream LLM providers. Every request and response passes through it, making it the natural enforcement point for cost controls. AI Gateway exposes rate limits and usage metadata that you can combine with Durable Objects or KV to implement per-user, per-feature, or global token-budget caps without any changes to your model calling code.

## Tracking Token Usage via AI Gateway Logs

AI Gateway logs include `usage.prompt_tokens` and `usage.completion_tokens` for each request. Read these from the response metadata or the gateway's Logpush stream to feed a rolling budget counter.

```typescript
// src/gateway-client.ts
interface Env {
  AI_GATEWAY_ACCOUNT_ID: string;
  AI_GATEWAY_ID: string;
  AI_GATEWAY_TOKEN: string;
  SPEND_KV: KVNamespace;
}

interface GatewayUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

// Cost per 1 000 tokens in USD (update to match your provider contract)
const COST_PER_1K: Record<string, { prompt: number; completion: number }> = {
  "gpt-4o":                    { prompt: 0.005, completion: 0.015 },
  "claude-3-5-sonnet-20241022": { prompt: 0.003, completion: 0.015 },
  "@cf/meta/llama-3.1-8b-instruct": { prompt: 0.0000, completion: 0.0000 }, // Workers AI flat rate
};

function estimateCostUSD(model: string, usage: GatewayUsage): number {
  const rates = COST_PER_1K[model] ?? { prompt: 0.002, completion: 0.008 };
  return (
    (usage.prompt_tokens    / 1000) * rates.prompt +
    (usage.completion_tokens / 1000) * rates.completion
  );
}
```

## Enforcing Per-User Daily Budgets with KV

```typescript
// src/budget.ts
const DAILY_BUDGET_USD = 0.50;  // $0.50 per user per day
const GLOBAL_DAILY_CAP = 50.00; // $50 global daily ceiling

interface BudgetEntry {
  spentUSD: number;
  resetAt: number; // epoch ms
}

function todayKey(prefix: string): string {
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  return `${prefix}:${today}`;
}

async function checkAndDebitBudget(
  kv: KVNamespace,
  userId: string,
  estimatedCost: number
): Promise<{ allowed: boolean; remainingUSD: number }> {
  const userKey  = todayKey(`budget:user:${userId}`);
  const globalKey = todayKey("budget:global");

  const [userRaw, globalRaw] = await Promise.all([
    kv.get(userKey,   "json") as Promise<BudgetEntry | null>,
    kv.get(globalKey, "json") as Promise<BudgetEntry | null>,
  ]);

  const now = Date.now();
  const midnightMs = new Date().setUTCHours(24, 0, 0, 0);

  const userEntry:   BudgetEntry = userRaw   ?? { spentUSD: 0, resetAt: midnightMs };
  const globalEntry: BudgetEntry = globalRaw ?? { spentUSD: 0, resetAt: midnightMs };

  if (userEntry.spentUSD + estimatedCost > DAILY_BUDGET_USD) {
    return { allowed: false, remainingUSD: DAILY_BUDGET_USD - userEntry.spentUSD };
  }

  if (globalEntry.spentUSD + estimatedCost > GLOBAL_DAILY_CAP) {
    return { allowed: false, remainingUSD: GLOBAL_DAILY_CAP - globalEntry.spentUSD };
  }

  // Debit both counters atomically (best-effort — KV is eventually consistent)
  const ttl = Math.ceil((midnightMs - now) / 1000);
  await Promise.all([
    kv.put(userKey,   JSON.stringify({ ...userEntry,   spentUSD: userEntry.spentUSD   + estimatedCost }), { expirationTtl: ttl }),
    kv.put(globalKey, JSON.stringify({ ...globalEntry, spentUSD: globalEntry.spentUSD + estimatedCost }), { expirationTtl: ttl }),
  ]);

  return { allowed: true, remainingUSD: DAILY_BUDGET_USD - (userEntry.spentUSD + estimatedCost) };
}
```

## Gateway Middleware Worker

Wire budget checks in front of every AI call. Use a pre-flight estimated cost based on prompt token count, then reconcile with actual usage from the response.

```typescript
// src/index.ts
import { estimateCostUSD, type GatewayUsage } from "./gateway-client";
import { checkAndDebitBudget } from "./budget";

interface Env {
  AI: Ai;
  SPEND_KV: KVNamespace;
}

const MODEL = "@cf/meta/llama-3.1-8b-instruct";
const ACCOUNT = "<YOUR_CF_ACCOUNT_ID>";
const GATEWAY = "my-ai-gateway";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { userId, prompt } = await request.json<{ userId: string; prompt: string }>();

    // Rough pre-flight estimate: 1 token ≈ 4 chars
    const estimatedPromptTokens = Math.ceil(prompt.length / 4);
    const estimatedCost = (estimatedPromptTokens / 1000) * 0.002;

    const { allowed, remainingUSD } = await checkAndDebitBudget(
      env.SPEND_KV, userId, estimatedCost
    );

    if (!allowed) {
      return Response.json(
        { error: "daily_budget_exceeded", remainingUSD },
        { status: 429 }
      );
    }

    // Route through AI Gateway for logging + rate-limiting
    const gatewayUrl = `https://gateway.ai.cloudflare.com/v1/${ACCOUNT}/${GATEWAY}/workers-ai/${MODEL}`;

    const upstream = await fetch(gatewayUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${request.headers.get("cf-access-token") ?? ""}`,
      },
      body: JSON.stringify({
        messages: [
          { role: "system", content: "You are a helpful assistant." },
          { role: "user",   content: prompt },
        ],
        max_tokens: 512,
      }),
    });

    const data = await upstream.json<{ usage?: GatewayUsage; choices?: Array<{ message: { content: string } }> }>();

    // Reconcile actual usage — adjust KV counter in background
    if (data.usage) {
      const actualCost = estimateCostUSD(MODEL, data.usage);
      const drift = actualCost - estimatedCost;
      if (Math.abs(drift) > 0.0001) {
        ctx.waitUntil(
          checkAndDebitBudget(env.SPEND_KV, userId, drift)
        );
      }
    }

    return Response.json({
      response: data.choices?.[0]?.message?.content ?? "",
      usage: data.usage,
      remainingUSD,
    });
  },
};
```

## Hard Limits via AI Gateway Rate Limiting Rules

Beyond KV-based soft limits, configure gateway-level hard limits in the Cloudflare dashboard or via API. These block requests before they leave the CF edge.

```typescript
// Configure via Cloudflare API — run once during infrastructure setup
async function createGatewayRateLimit(accountId: string, gatewayId: string, token: string) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai-gateway/gateways/${gatewayId}/rate-limits`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        name: "global-rpm-cap",
        description: "Global requests per minute ceiling",
        limitBy: "gateway",       // or "consumer", "header:x-user-id"
        requestsPerPeriod: 1000,
        period: "60s",
        action: "block",          // or "queue" if you want to hold requests
      }),
    }
  );
  return res.json();
}
```

## Alerting on Budget Thresholds

Use Cloudflare Workers Analytics Engine to emit spend events and trigger Cloudflare Notifications when thresholds are approached.

```typescript
interface Env {
  SPEND_KV: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
  ALERT_WEBHOOK: string;
}

async function emitSpendEvent(
  env: Env,
  ctx: ExecutionContext,
  userId: string,
  costUSD: number,
  remainingUSD: number
) {
  env.ANALYTICS.writeDataPoint({
    blobs:   [userId, "ai_spend"],
    doubles: [costUSD, remainingUSD],
    indexes: [userId],
  });

  // Alert when user is within 10% of daily cap
  const DAILY_CAP = 0.50;
  if (remainingUSD / DAILY_CAP < 0.1) {
    ctx.waitUntil(
      fetch(env.ALERT_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userId,
          message: `Budget alert: user ${userId} has $${remainingUSD.toFixed(4)} remaining today`,
          remainingUSD,
        }),
      })
    );
  }
}
```

## Anti-patterns
- Enforcing budgets only in application code but not at the gateway — a misconfigured client can bypass application logic
- Using global counters without per-user partitioning — one heavy user starves everyone else
- Pre-flight estimates without reconciliation — long responses with many completion tokens will under-debit
- Blocking the request while waiting for KV writes — debit in `ctx.waitUntil()` for non-critical adjustments
- Hard-coding cost tables without a refresh mechanism — provider pricing changes; externalise to KV or D1

## Gotchas
- KV is eventually consistent; under very high concurrency two Workers might both read a budget under-cap and both proceed, creating a small overage window — use Durable Objects for strict serialisation if that matters
- AI Gateway rate-limit rules count requests, not tokens — combine with application-level token counting for cost accuracy
- Workers AI models billed via platform subscription don't have per-token cost but do have request and token rate limits — still useful to track for capacity planning
- The `cf-aig-*` response headers from AI Gateway contain request IDs useful for correlating logs to KV budget entries

## Verification
```bash
# Simulate budget exhaustion: fire >$0.50 worth of requests with a tiny cap
# Then assert subsequent requests return 429
for i in $(seq 1 20); do
  curl -sX POST http://localhost:8787/ \
    -H "Content-Type: application/json" \
    -d "{\"userId\":\"test-user\",\"prompt\":\"Write a 200 word essay about AI.\"}" \
    | jq -r '.error // .response | .[0:60]'
done

# Confirm KV entry contains updated spend
wrangler kv key get --binding=SPEND_KV "budget:user:test-user:$(date +%Y-%m-%d)"
```

## Related
- [ai-gateway-rate-limiting.md](ai-gateway-rate-limiting.md)
- [ai-gateway-request-caching-cost-control.md](ai-gateway-request-caching-cost-control.md)
- [ai-cost-monitoring.md](ai-cost-monitoring.md)
- [llm-cost-optimization.md](llm-cost-optimization.md)
- [ai-gateway-logging.md](ai-gateway-logging.md)

## Sources
- Cloudflare AI Gateway rate limiting docs: https://developers.cloudflare.com/ai-gateway/configuration/rate-limiting/
- Cloudflare KV consistency model: https://developers.cloudflare.com/kv/learning/how-kv-works/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
