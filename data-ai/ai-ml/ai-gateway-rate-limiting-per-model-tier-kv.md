# AI Gateway Rate Limiting per Model Tier with Workers KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project exposes an AI-assisted writing tool to users at three subscription tiers:
Free, Plus, and Pro. Each tier is allowed a different quota of AI completions per day,
and different model families are available per tier (e.g. Free users get
`llama-3.1-8b-instruct`; Pro users get `llama-3.1-70b-instruct` or GPT-4o via AI
Gateway's universal endpoint). Without per-model-tier enforcement at the edge, a Free
user can call the 70B model endpoint directly and bypass both the quota and the cost
tier, blowing the platform's inference budget.

Goal: enforce model-tier access control and per-day quota at the Workers layer, using
KV as the fast counter store, before requests reach AI Gateway, with zero database
round-trips on the hot path.

---

## Context

Cloudflare AI Gateway sits between the application Worker and upstream model providers.
Rate limiting native to AI Gateway (as of 2026) applies globally to a gateway or per
API key, not per-user per-model-tier. The application therefore must enforce user-
facing quotas before the request hits the gateway.

Architecture:
1. **Worker** receives the AI completion request with a session token.
2. Worker resolves `userId + tier` from a KV or Durable Object session cache.
3. Worker checks and increments a per-user per-tier counter in KV.
4. If within quota, Worker rewrites the request to AI Gateway with the tier-appropriate
   model, attaches the gateway API key, and streams the response back.
5. If over quota, Worker returns `429` with a `Retry-After` header.

KV is chosen for the counter because:
- Sub-millisecond read latency at the edge
- Eventual consistency is acceptable (a Free user might get 1–2 extra requests in a
  race, which is tolerable; exact accounting lives in D1 refreshed hourly)
- KV TTL handles counter expiry at midnight UTC automatically

---

## Tier Configuration

```typescript
// src/config/tiers.ts
export type UserTier = "free" | "plus" | "pro";

export interface TierConfig {
  dailyRequestLimit: number;
  allowedModels: string[];
  gatewayModel: string;        // the model string forwarded to AI Gateway
  maxTokensPerRequest: number;
}

export const TIER_CONFIG: Record<UserTier, TierConfig> = {
  free: {
    dailyRequestLimit: 20,
    allowedModels: ["llama-3.1-8b-instruct"],
    gatewayModel: "@cf/meta/llama-3.1-8b-instruct",
    maxTokensPerRequest: 512,
  },
  plus: {
    dailyRequestLimit: 200,
    allowedModels: ["llama-3.1-8b-instruct", "llama-3.1-70b-instruct"],
    gatewayModel: "@cf/meta/llama-3.1-70b-instruct",
    maxTokensPerRequest: 2048,
  },
  pro: {
    dailyRequestLimit: 2000,
    allowedModels: [
      "llama-3.1-70b-instruct",
      "gpt-4o",
      "claude-3-5-sonnet",
    ],
    gatewayModel: "openai/gpt-4o",   // AI Gateway universal endpoint model string
    maxTokensPerRequest: 8192,
  },
};
```

---

## KV Counter Helpers

```typescript
// src/lib/quota.ts
export interface Env {
  RATE_LIMIT_KV: KVNamespace;
  DB: D1Database;
}

/** Returns the KV key for a user's daily counter. Rotates at midnight UTC. */
function quotaKey(userId: string, tier: UserTier): string {
  const dayStamp = new Date().toISOString().slice(0, 10); // "2026-08-23"
  return `quota:${tier}:${userId}:${dayStamp}`;
}

/**
 * Atomically increment a user's daily request count.
 * Returns { allowed: boolean; current: number; limit: number }.
 *
 * KV does not support atomic increment natively; we use a Durable Object for
 * strict enforcement (see below) or accept the eventual-consistency race on KV.
 */
export async function checkAndIncrementQuota(
  env: Env,
  userId: string,
  tier: UserTier
): Promise<{ allowed: boolean; current: number; limit: number }> {
  const config = TIER_CONFIG[tier];
  const key = quotaKey(userId, tier);

  const raw = await env.RATE_LIMIT_KV.get(key);
  const current = raw ? parseInt(raw, 10) : 0;

  if (current >= config.dailyRequestLimit) {
    return { allowed: false, current, limit: config.dailyRequestLimit };
  }

  // Increment; TTL expires at end of day (86 400 s is approximate; DO gives exact).
  // We use ctx.waitUntil in the Worker to avoid blocking the response on the put.
  const next = current + 1;
  await env.RATE_LIMIT_KV.put(key, String(next), { expirationTtl: 90000 });

  return { allowed: true, current: next, limit: config.dailyRequestLimit };
}

/** Verify the requested model is permitted for the user's tier. */
export function modelAllowedForTier(
  requestedModel: string,
  tier: UserTier
): boolean {
  return TIER_CONFIG[tier].allowedModels.some((m) =>
    requestedModel.includes(m)
  );
}
```

---

## Main Worker: Gate Before AI Gateway

```typescript
// src/index.ts
import { checkAndIncrementQuota, modelAllowedForTier } from "./lib/quota";
import { TIER_CONFIG, UserTier } from "./config/tiers";

export interface Env {
  RATE_LIMIT_KV: KVNamespace;
  SESSION_KV: KVNamespace;
  DB: D1Database;
  // AI Gateway universal endpoint base URL (set in wrangler.toml [vars])
  AI_GATEWAY_URL: string;
  AI_GATEWAY_TOKEN: string;
}

interface SessionData {
  userId: string;
  tier: UserTier;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // 1. Resolve session
    const sessionToken = request.headers.get("X-Session-Token");
    if (!sessionToken) {
      return jsonError("Unauthorized", 401);
    }

    const sessionRaw = await env.SESSION_KV.get(sessionToken);
    if (!sessionRaw) {
      return jsonError("Invalid or expired session", 401);
    }

    const { userId, tier } = JSON.parse(sessionRaw) as SessionData;
    const tierConfig = TIER_CONFIG[tier];

    // 2. Validate requested model against tier
    const body = await request.json<{
      model?: string;
      messages: unknown[];
      max_tokens?: number;
    }>();

    if (body.model && !modelAllowedForTier(body.model, tier)) {
      return jsonError(
        `Model '${body.model}' is not available on the ${tier} plan`,
        403
      );
    }

    // 3. Check and increment quota
    const quota = await checkAndIncrementQuota(env, userId, tier);
    if (!quota.allowed) {
      const resetAt = new Date();
      resetAt.setUTCHours(24, 0, 0, 0);
      return new Response(
        JSON.stringify({
          error: "Daily quota exceeded",
          limit: quota.limit,
          resetAt: resetAt.toISOString(),
        }),
        {
          status: 429,
          headers: {
            "Content-Type": "application/json",
            "Retry-After": String(
              Math.ceil((resetAt.getTime() - Date.now()) / 1000)
            ),
            "X-RateLimit-Limit": String(quota.limit),
            "X-RateLimit-Remaining": "0",
          },
        }
      );
    }

    // 4. Rewrite request to AI Gateway with tier-appropriate model
    const upstreamBody = {
      ...body,
      model: tierConfig.gatewayModel,
      max_tokens: Math.min(
        body.max_tokens ?? tierConfig.maxTokensPerRequest,
        tierConfig.maxTokensPerRequest
      ),
    };

    const gatewayRes = await fetch(
      `${env.AI_GATEWAY_URL}/v1/chat/completions`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.AI_GATEWAY_TOKEN}`,
          "cf-aig-metadata": JSON.stringify({ userId, tier }),
        },
        body: JSON.stringify(upstreamBody),
      }
    );

    // Pass through response headers + add quota headers
    const responseHeaders = new Headers(gatewayRes.headers);
    responseHeaders.set("X-RateLimit-Limit", String(quota.limit));
    responseHeaders.set(
      "X-RateLimit-Remaining",
      String(quota.limit - quota.current)
    );

    return new Response(gatewayRes.body, {
      status: gatewayRes.status,
      headers: responseHeaders,
    });
  },
};

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
```

---

## Exact Enforcement with a Durable Object (Optional)

For Pro users where every over-quota request has direct cost, use a Durable Object
to guarantee atomic increment:

```typescript
// src/do/quota-counter.ts
export class QuotaCounter implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const { limit } = await request.json<{ limit: number }>();
    const count = (await this.state.storage.get<number>("count")) ?? 0;

    if (count >= limit) {
      return Response.json({ allowed: false, count });
    }

    await this.state.storage.put("count", count + 1);
    return Response.json({ allowed: true, count: count + 1 });
  }
}
```

```typescript
// Usage in main Worker for "pro" tier only:
async function checkProQuota(env: Env & { QUOTA_DO: DurableObjectNamespace }, userId: string) {
  const id = env.QUOTA_DO.idFromName(`pro:${userId}:${new Date().toISOString().slice(0, 10)}`);
  const stub = env.QUOTA_DO.get(id);
  return stub.fetch("http://do/check", {
    method: "POST",
    body: JSON.stringify({ limit: TIER_CONFIG.pro.dailyRequestLimit }),
  }).then((r) => r.json<{ allowed: boolean; count: number }>());
}
```

---

## Hourly D1 Reconciliation

KV is the fast path; D1 is the source of truth for billing and audit:

```typescript
// src/cron/reconcile-quotas.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const today = new Date().toISOString().slice(0, 10);
    const { keys } = await env.RATE_LIMIT_KV.list({ prefix: `quota:` });

    for (const key of keys) {
      // key.name = "quota:<tier>:<userId>:<date>"
      const parts = key.name.split(":");
      if (parts.length !== 4 || parts[3] !== today) continue;
      const [, tier, userId] = parts;
      const count = await env.RATE_LIMIT_KV.get(key.name);

      await env.DB.prepare(
        `INSERT INTO daily_quota_usage (user_id, tier, date, request_count)
         VALUES (?, ?, ?, ?)
         ON CONFLICT (user_id, date) DO UPDATE SET request_count = excluded.request_count`
      )
        .bind(userId, tier, today, parseInt(count ?? "0", 10))
        .run();
    }
  },
};
```

---

## Anti-patterns

- **Using a single global AI Gateway rate-limit header** for all users — AI Gateway's
  built-in rate limits apply per gateway, not per user or model tier.
- **Trusting the `model` field from the client** to determine cost — always rewrite
  to the tier-appropriate `gatewayModel` server-side regardless of what the client
  sends.
- **Blocking the response on the KV write** — put the KV increment inside
  `ctx.waitUntil()` for Free/Plus tiers to avoid adding latency; use the DO for Pro.
- **Not expiring KV keys** — without `expirationTtl`, quota keys accumulate
  indefinitely; set TTL to 90 000 s (25 h) to ensure cleanup even if midnight
  boundary logic has edge cases.

---

## Gotchas

- KV reads from PoP cache can be up to 60 s stale. In practice, a Free user could
  send ~20 concurrent requests and get all 20 allowed if the first write has not
  propagated. This is acceptable for the example project use case; use the DO for strict
  enforcement.
- AI Gateway's `cf-aig-metadata` header is indexed in the gateway's log but is NOT
  used for rate limiting by the gateway itself — it is only for log correlation.
- A tier upgrade during the day should reset the quota counter. Handle this by
  writing a new KV key under the new tier and expiring the old one explicitly.
- Model availability on AI Gateway's universal endpoint changes; pin a fallback model
  in `TIER_CONFIG` and handle `502`/`503` from the gateway with a retry.

---

## Verification

1. Create test sessions for each tier in `SESSION_KV`.
2. Send `dailyRequestLimit + 1` requests for each tier; confirm request N+1 returns
   `429` with correct `Retry-After` and `X-RateLimit-*` headers.
3. Attempt to call a Pro model from a Free session; confirm `403` with model mismatch
   message.
4. Wait for the reconciliation cron to fire; query D1
   `SELECT * FROM daily_quota_usage WHERE date = '2026-08-23'` and confirm counts
   match KV values.
5. Tail AI Gateway logs and confirm `cf-aig-metadata` shows the correct `userId` and
   `tier` for each request.

---

## Related

- `ai-gateway-rate-limiting.md`
- `ai-gateway-cost-attribution-per-tenant-d1.md`
- `ai-gateway-budget-caps-spend-control.md`
- `ai-gateway-model-routing-latency-cost-workers.md`
- `llm-rate-limit-handling.md`

---

## Sources

- Cloudflare AI Gateway rate limiting: https://developers.cloudflare.com/ai-gateway/configuration/rate-limiting/
- Workers KV: https://developers.cloudflare.com/kv/
- Durable Objects: https://developers.cloudflare.com/durable-objects/
- AI Gateway universal endpoint: https://developers.cloudflare.com/ai-gateway/providers/universal/
