# api-rate-limit-by-key

**Issue:** Rate limit per API key, per user, per tenant
**Date:** 2026-08-09
**Status:** documented

## Symptom
A single user makes 10k requests/minute to your API. Other
users see timeouts. The single user's behavior exhausts the
CF Workers request budget. You have no way to throttle just
that user.

## Root cause
**Global rate limits** (per IP, per CF zone) are too coarse.
A single misbehaving client can starve everyone. **Per-key rate
limits** (per API key, per user) are the right granularity.

**Source:** Stripe rate limiting:
https://stripe.com/docs/rate-limits

> "Stripe uses a token bucket algorithm with per-second
> refill rates, scoped to the API key."

## The pattern: per-key token bucket

```ts
// In a Durable Object (per API key)
class RateLimitDO {
  private tokens: number;
  private lastRefill: number;

  constructor(state: DurableObjectState, env: Env) {
    this.tokens = 100;  // burst capacity
    this.lastRefill = Date.now();
  }

  async fetch(req: Request): Promise<Response> {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    // Refill at 10 tokens/sec
    this.tokens = Math.min(100, this.tokens + elapsed * 10);
    this.lastRefill = now;

    if (this.tokens < 1) {
      const retryAfter = Math.ceil((1 - this.tokens) / 10);
      return new Response('Rate limited', {
        status: 429,
        headers: {
          'Retry-After': String(retryAfter),
          'X-RateLimit-Limit': '100',
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Reset': String(Math.ceil((now + retryAfter * 1000) / 1000)),
        },
      });
    }

    this.tokens -= 1;
    return new Response('OK', {
      status: 200,
      headers: {
        'X-RateLimit-Limit': '100',
        'X-RateLimit-Remaining': String(Math.floor(this.tokens)),
      },
    });
  }
}

// Usage
async function checkRateLimit(apiKey: string, env: Env): Promise<Response | null> {
  const id = env.RATE_LIMIT_DO.idFromName(apiKey);
  const stub = env.RATE_LIMIT_DO.get(id);
  const result = await stub.fetch('https://do/check');
  if (result.status === 429) return result;
  return null;  // OK
}
```

## Per-tier limits

Different API key tiers have different limits:

| Tier | Burst | Refill | Monthly cap |
|---|---|---|---|
| Free | 10 | 1/sec | 10k |
| Pro | 100 | 10/sec | 1M |
| Enterprise | 1000 | 100/sec | Unlimited |

```ts
function getTierLimits(tier: string): { burst: number; refill: number; monthlyCap: number } {
  switch (tier) {
    case 'free': return { burst: 10, refill: 1, monthlyCap: 10_000 };
    case 'pro': return { burst: 100, refill: 10, monthlyCap: 1_000_000 };
    case 'enterprise': return { burst: 1000, refill: 100, monthlyCap: Number.MAX_SAFE_INTEGER };
    default: return { burst: 10, refill: 1, monthlyCap: 10_000 };
  }
}
```

## Monthly caps

Token bucket handles per-second throttling. For monthly caps,
use a separate counter in D1:

```ts
// Monthly usage counter
async function recordMonthlyUsage(apiKey: string, env: Env): Promise<{ allowed: boolean; remaining: number }> {
  const now = new Date();
  const yearMonth = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}`;

  // Atomic increment
  const result = await env.DB!.prepare(
    `INSERT INTO api_usage (api_key_id, year_month, request_count)
     VALUES (?, ?, 1)
     ON CONFLICT(api_key_id, year_month) DO UPDATE SET request_count = request_count + 1
     RETURNING request_count`
  ).bind(apiKey, yearMonth).first<{ request_count: number }>();

  const tier = await getApiKeyTier(apiKey, env);
  const remaining = tier.monthlyCap - result!.request_count;
  return { allowed: remaining > 0, remaining: Math.max(0, remaining) };
}
```

## Per-tenant vs per-user

For multi-tenant APIs:
- **Per API key:** the key holder's tier
- **Per user:** the user (if authenticated)
- **Per tenant:** the tenant (across all users + keys)

A noisy tenant should be throttled even if individual users
behave:

```ts
async function checkAllRateLimits(request: Request, env: Env): Promise<Response | null> {
  const apiKey = await getApiKeyFromRequest(request);
  const user = await authenticate(request, env);
  const tenantId = user?.tenantId;

  // Check per-key
  if (apiKey) {
    const r = await checkRateLimit(`key:${apiKey.id}`, env);
    if (r) return r;
  }
  // Check per-user
  if (user) {
    const r = await checkRateLimit(`user:${user.id}`, env);
    if (r) return r;
  }
  // Check per-tenant
  if (tenantId) {
    const r = await checkRateLimit(`tenant:${tenantId}`, env);
    if (r) return r;
  }
  return null;
}
```

The first one to return 429 wins. Each is independent.

## Verification
- **Test:** `test/rate-limit.test.ts > per-key limit honored,
  per-user limit independent` — passes
- **Live:** The 429 response includes `Retry-After` +
  `X-RateLimit-*` headers
- **Audit:** Quarterly review of rate limit configuration

## Gotchas
- **Token bucket state in DO is per-instance.** A new DO
  starts with `tokens = burst`. After eviction, the state
  resets. For persistent state, write to DO storage.
- **The 429 response should include `Retry-After` AND
  `X-RateLimit-Reset`** — clients use the latter for
  exponential backoff.
- **Monthly caps are UTC-based.** Pick a consistent time zone
  (UTC is standard) to avoid drift.
- **Don't share rate limit state across deployments.** A
  blue-green deploy creates a new isolate; the rate limit
  state is fresh.
- **The DO has a 50ms cold start.** For latency-sensitive
  paths, pre-warm with a cron ping.

## Related
- `rate-limiting-strategies.md`
- `circuit-breaker-pattern.md`
- `per-tenant-durable-object.md`
- Stripe: https://stripe.com/docs/rate-limits
- Cloudflare Rate Limiting: https://developers.cloudflare.com/waf/rate-limiting-rules/
