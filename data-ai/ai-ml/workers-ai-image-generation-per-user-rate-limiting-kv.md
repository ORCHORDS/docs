# Workers AI Image Generation Per-User Rate Limiting with KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A single heavy user is calling your image generation endpoint thousands of times per day, exhausting your Workers AI image quota and degrading service for other users. You need per-user rate limits enforced at the Worker edge, before the AI model is ever invoked, with zero external dependencies.

## Context

Workers KV is ideal for lightweight rate-limit counters: it is globally consistent enough for "best-effort" quota enforcement at the edge, has sub-millisecond read latency in most regions, and supports atomic expiring keys. The pattern uses a sliding-window counter stored in KV, keyed by `userId:bucket`, where `bucket` is the current time window (e.g., the current UTC hour or day). Limits are tiered: free users get fewer generations per day than paid users.

---

## 1. KV Rate-limit Counter Helper

```typescript
export interface Env {
  AI: Ai;
  RATE_LIMITS: KVNamespace;
}

export interface RateLimitConfig {
  maxRequests: number;   // allowed per window
  windowSeconds: number; // window size in seconds
}

const TIERS: Record<string, RateLimitConfig> = {
  free: { maxRequests: 5, windowSeconds: 86400 },   // 5 per day
  pro: { maxRequests: 50, windowSeconds: 86400 },    // 50 per day
  enterprise: { maxRequests: 500, windowSeconds: 3600 }, // 500 per hour
};

function rateKey(userId: string, windowSeconds: number): string {
  const bucket = Math.floor(Date.now() / 1000 / windowSeconds);
  return `rl:img:${userId}:${bucket}`;
}

interface RateLimitResult {
  allowed: boolean;
  current: number;
  limit: number;
  resetAt: number; // unix seconds
}

export async function checkRateLimit(
  kv: KVNamespace,
  userId: string,
  tier: string,
): Promise<RateLimitResult> {
  const config = TIERS[tier] ?? TIERS.free;
  const key = rateKey(userId, config.windowSeconds);
  const bucket = Math.floor(Date.now() / 1000 / config.windowSeconds);
  const resetAt = (bucket + 1) * config.windowSeconds;

  const raw = await kv.get(key);
  const current = raw ? parseInt(raw, 10) : 0;

  return {
    allowed: current < config.maxRequests,
    current,
    limit: config.maxRequests,
    resetAt,
  };
}

export async function incrementRateLimit(
  kv: KVNamespace,
  userId: string,
  tier: string,
): Promise<void> {
  const config = TIERS[tier] ?? TIERS.free;
  const key = rateKey(userId, config.windowSeconds);

  const raw = await kv.get(key);
  const current = raw ? parseInt(raw, 10) : 0;
  await kv.put(key, String(current + 1), {
    expirationTtl: config.windowSeconds * 2, // keep one extra window for debugging
  });
}
```

## 2. Worker Handler with Pre-flight Rate Check

```typescript
const IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell";

function getUserId(request: Request): string | null {
  // Extract from JWT sub, header, or cookie — example uses a header
  return request.headers.get("x-user-id");
}

function getUserTier(request: Request): string {
  return request.headers.get("x-user-tier") ?? "free";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST only", { status: 405 });
    }

    const userId = getUserId(request);
    if (!userId) return new Response("Unauthorized", { status: 401 });

    const tier = getUserTier(request);

    // 1. Pre-flight rate-limit check (read-only)
    const rl = await checkRateLimit(env.RATE_LIMITS, userId, tier);

    if (!rl.allowed) {
      return Response.json(
        {
          error: "Rate limit exceeded",
          limit: rl.limit,
          current: rl.current,
          resetAt: rl.resetAt,
          retryAfter: rl.resetAt - Math.floor(Date.now() / 1000),
        },
        {
          status: 429,
          headers: {
            "Retry-After": String(rl.resetAt - Math.floor(Date.now() / 1000)),
            "X-RateLimit-Limit": String(rl.limit),
            "X-RateLimit-Remaining": String(rl.limit - rl.current),
            "X-RateLimit-Reset": String(rl.resetAt),
          },
        },
      );
    }

    // 2. Parse request body
    const { prompt, steps, width, height } = await request.json<{
      prompt: string;
      steps?: number;
      width?: number;
      height?: number;
    }>();

    if (!prompt) return new Response("Missing prompt", { status: 400 });

    // 3. Increment counter *before* inference to prevent race-condition over-usage
    await incrementRateLimit(env.RATE_LIMITS, userId, tier);

    // 4. Run image generation
    const result = await env.AI.run(IMAGE_MODEL, {
      prompt,
      num_steps: steps ?? 4,
      width: width ?? 1024,
      height: height ?? 1024,
    });

    return new Response(result, {
      headers: {
        "Content-Type": "image/png",
        "X-RateLimit-Remaining": String(rl.limit - rl.current - 1),
        "X-RateLimit-Reset": String(rl.resetAt),
      },
    });
  },
};
```

## 3. Atomic Compare-and-Swap Approach for High Concurrency

```typescript
// For users with very high concurrency (enterprise tier), the read-then-write
// in checkRateLimit + incrementRateLimit has a small race window.
// Use a Durable Object for strict atomic counting in those cases.

export class RateLimiterDO {
  private state: DurableObjectState;
  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const { userId, limit, windowSeconds } =
      await request.json<{ userId: string; limit: number; windowSeconds: number }>();

    const bucket = Math.floor(Date.now() / 1000 / windowSeconds);
    const storageKey = `${userId}:${bucket}`;

    const current = (await this.state.storage.get<number>(storageKey)) ?? 0;

    if (current >= limit) {
      return Response.json({ allowed: false, current });
    }

    await this.state.storage.put(storageKey, current + 1);
    await this.state.storage.setAlarm(
      new Date((bucket + 2) * windowSeconds * 1000),
    );

    return Response.json({ allowed: true, current: current + 1 });
  }

  async alarm(): Promise<void> {
    await this.state.storage.deleteAll();
  }
}
```

## 4. Usage Reporting Endpoint

```typescript
export async function usageEndpoint(
  request: Request,
  env: Env,
): Promise<Response> {
  const userId = getUserId(request);
  if (!userId) return new Response("Unauthorized", { status: 401 });

  const tier = getUserTier(request);
  const rl = await checkRateLimit(env.RATE_LIMITS, userId, tier);

  return Response.json({
    userId,
    tier,
    used: rl.current,
    limit: rl.limit,
    remaining: Math.max(0, rl.limit - rl.current),
    resetAt: new Date(rl.resetAt * 1000).toISOString(),
    percentUsed: Math.round((rl.current / rl.limit) * 100),
  });
}
```

## 5. Admin Override — Resetting a User's Counter

```typescript
export async function adminResetRateLimit(
  env: Env,
  userId: string,
  tier: string,
): Promise<void> {
  const config = TIERS[tier] ?? TIERS.free;
  const key = rateKey(userId, config.windowSeconds);
  await env.RATE_LIMITS.delete(key);
}

// Usage in an admin-gated endpoint:
// if (isAdmin(request)) {
//   const { userId, tier } = await request.json();
//   await adminResetRateLimit(env, userId, tier);
//   return Response.json({ reset: true });
// }
```

---

## Anti-patterns

- **Checking the rate limit *after* running inference** — the AI call may succeed before the limit is enforced, allowing over-usage. Increment before dispatching the AI call.
- **Using a single global KV key without a time bucket** — a monotonically incrementing counter never resets and cannot implement windowed quotas; always include a time bucket in the key.
- **Relying on KV for strict atomicity** — KV uses eventual consistency; two concurrent requests from the same user may both read `current=4` against a limit of 5 and both proceed. For strict limits, use a Durable Object (section 3).
- **Setting `expirationTtl` equal to `windowSeconds`** — if the Worker clock is slightly off, the key may expire before the window ends. Use `2 × windowSeconds` to prevent premature expiry while keeping storage clean.

## Gotchas

- `@cf/black-forest-labs/flux-1-schnell` returns raw binary PNG data, not a JSON object. The `Content-Type: image/png` header must be set on the response; failing to do so causes browsers to display garbage.
- Workers AI image generation models accept `num_steps`, not `steps`; confirm the exact parameter name in the model card — it differs between Flux and Stable Diffusion variants.
- KV `get` returns `null` when a key does not exist, not `"0"`; always handle the null case to avoid `NaN` counter values.
- Returning the Retry-After header in seconds (not a date) is required by RFC 9110; some clients ignore the header if the format is wrong.

## Verification

```bash
# Exhaust a free-tier user's daily limit (5 requests)
for i in {1..6}; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    https://my-worker.workers.dev/generate \
    -H "x-user-id: user-abc" \
    -H "x-user-tier: free" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"A sunset over the ocean"}')
  echo "Request $i: HTTP $STATUS"
done
# Expected: 200 for requests 1-5, 429 for request 6

# Check remaining quota
curl https://my-worker.workers.dev/usage \
  -H "x-user-id: user-abc" \
  -H "x-user-tier: free"
# Expected: {"used":5,"limit":5,"remaining":0,...}
```

## Related

- `ai-gateway-rate-limiting-per-model-tier-kv.md`
- `workers-ai-image-generation-flux-stable-diffusion.md`
- `workers-ai-image-generation-prompt-optimization-r2-gallery.md`
- `ai-gateway-budget-caps-spend-control.md`
- `workers-ai-durable-objects-stateful-sessions.md`

## Sources

- Workers AI Flux image generation: https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/
- Cloudflare KV write API (TTL): https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- RFC 9110 — Retry-After header: https://www.rfc-editor.org/rfc/rfc9110#field.retry-after
