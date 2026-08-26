# feature-cookbook-rate-limiting

**Issue:** Rate limiting — dimensions, algorithms, response
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user is hitting your API at 1000 req/sec. The DB is
overwhelmed. Other users see errors. You block the IP.
The user is using a legit app with a bug. You unblock.
The bug is fixed, but the IP is still blocked.

## Root cause
**Without rate limiting, one user can DoS the system.**

**Source:** Stripe rate limiting:
https://stripe.com/docs/rate-limits

## The "per-IP" pattern

For anonymous users, rate limit per IP:
```ts
async function checkIpRateLimit(ip: string, env: Env): Promise<{ allowed: boolean; remaining: number }> {
  const id = env.RATE_LIMIT.idFromName(`ip:${ip}`);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate-limit/check', {
    method: 'POST',
    body: JSON.stringify({ limit: 100, windowMs: 60_000 }),
  });
  return response.json();
}
```

The IP is rate-limited to 100 req/min.

## The "per-user" pattern

For authenticated users, rate limit per user:
```ts
async function checkUserRateLimit(userId: string, env: Env): Promise<{ allowed: boolean; remaining: number }> {
  const id = env.RATE_LIMIT.idFromName(`user:${userId}`);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate-limit/check', {
    method: 'POST',
    body: JSON.stringify({ limit: 1000, windowMs: 60_000 }),
  });
  return response.json();
}
```

The user is rate-limited to 1000 req/min.

## The "per-tenant" pattern

For multi-tenant, rate limit per tenant:
```ts
async function checkTenantRateLimit(tenantId: string, env: Env): Promise<{ allowed: boolean }> {
  const id = env.RATE_LIMIT.idFromName(`tenant:${tenantId}`);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate-limit/check', {
    method: 'POST',
    body: JSON.stringify({ limit: 10000, windowMs: 60_000 }),
  });
  return response.json();
}
```

The tenant is rate-limited to 10k req/min (across all
users).

## The "per-endpoint" pattern

For expensive endpoints, rate limit per endpoint:
```ts
async function checkEndpointRateLimit(userId: string, endpoint: string, env: Env): Promise<{ allowed: boolean }> {
  const id = env.RATE_LIMIT.idFromName(`endpoint:${userId}:${endpoint}`);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate-limit/check', {
    method: 'POST',
    body: JSON.stringify({ limit: 10, windowMs: 60_000 }),
  });
  return response.json();
}
```

The user is limited to 10 req/min on `/api/search`.

## The "tiered" pattern

For different limits per plan:
```ts
const PLAN_LIMITS = {
  free: { api: 100, search: 10 },
  pro: { api: 1000, search: 100 },
  enterprise: { api: 10000, search: 1000 },
};

async function checkRateLimit(user: User, endpoint: string, env: Env): Promise<{ allowed: boolean; remaining: number; resetAt: number }> {
  const limits = PLAN_LIMITS[user.plan];
  const limit = limits[endpoint] ?? 100;

  return checkUserRateLimit(user.id, endpoint, limit, env);
}
```

The limit is per plan.

## The "token bucket" pattern

For bursty traffic:
```ts
class TokenBucket {
  private tokens: number;
  private lastRefill: number;

  constructor(
    private capacity: number,
    private refillRate: number,  // tokens per second
  ) {
    this.tokens = capacity;
    this.lastRefill = Date.now();
  }

  consume(tokens = 1): boolean {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(this.capacity, this.tokens + elapsed * this.refillRate);
    this.lastRefill = now;

    if (this.tokens < tokens) return false;
    this.tokens -= tokens;
    return true;
  }
}
```

A token bucket allows bursts.

## The "rate limit response" pattern

For a rate-limited response, include the headers:
```ts
if (!allowed) {
  return new Response(JSON.stringify({
    type: 'https://example.com/probs/rate-limited',
    title: 'Rate limit exceeded',
    status: 429,
    code: 'RATE_LIMITED',
  }), {
    status: 429,
    headers: {
      'content-type': 'application/problem+json',
      'Retry-After': String(retryAfterSeconds),
      'X-RateLimit-Limit': String(limit),
      'X-RateLimit-Remaining': '0',
      'X-RateLimit-Reset': String(resetAt),
    },
  });
}
```

The client knows when to retry.

## The "IETF rate limit headers" pattern

Use the IETF draft:
- `RateLimit-Limit: 100`
- `RateLimit-Remaining: 0`
- `RateLimit-Reset: 60`

IETF draft: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/

## The "circuit breaker" pattern

For repeated failures, the rate limiter is "open":
```ts
class RateLimiter {
  private failures = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';

  async execute<T>(fn: () => Promise<T>, fallback: () => T): Promise<T> {
    if (this.state === 'open') return fallback();

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (err) {
      this.onFailure();
      return fallback();
    }
  }

  private onSuccess() {
    this.failures = 0;
    this.state = 'closed';
  }

  private onFailure() {
    this.failures++;
    if (this.failures >= 5) this.state = 'open';
  }
}
```

The circuit breaker fails fast when the rate limiter is
down.

## The "fail open" pattern

If the rate limiter is down, allow the request:
```ts
try {
  const { allowed } = await checkRateLimit(userId, env);
  if (!allowed) return new Response('Rate limited', { status: 429 });
} catch (err) {
  // Rate limiter is down; allow the request
  console.error({ msg: 'rate.limit.error', error: String(err) });
}

return next();
```

Failing open is safer than failing closed (which blocks
all users).

## The "user-friendly error" pattern

For a clear error message:
```ts
return new Response(JSON.stringify({
  type: 'https://example.com/probs/rate-limited',
  title: 'Rate limit exceeded',
  status: 429,
  detail: `You have made ${limit} requests in the last minute. Please wait ${retryAfter} seconds.`,
  code: 'RATE_LIMITED',
}), { status: 429, headers: { 'Retry-After': String(retryAfter) } });
```

The user knows what to do.

## The "metrics" pattern

Track rate limit metrics:
```ts
metrics.increment('rate_limit.checks_total', { result: 'allowed' });
metrics.increment('rate_limit.checks_total', { result: 'denied' });
```

The metrics show the rate limit's impact.

## The "dynamic limits" pattern

For limits that change based on system load:
```ts
async function getDynamicLimit(): Promise<number> {
  const cpuUsage = await getCpuUsage();
  if (cpuUsage > 0.8) return 50;  // Reduced limit
  if (cpuUsage > 0.6) return 100;
  return 1000;  // Normal limit
}
```

The limit adjusts based on load.

## The "whitelist" pattern

For trusted clients (internal services), bypass:
```ts
if (isInternalService(request) || isAdmin(ctx.user)) {
  return next();  // Bypass rate limit
}
```

Whitelisted clients are not rate-limited.

## Verification
- **Test:** Rate limit blocks at the limit
- **Test:** Rate limit allows under the limit
- **Live:** Rate limit metrics are monitored
- **Audit:** Quarterly review of limits

## Gotchas
- **The "fixed window boundary" gotcha.** A burst at the
  window boundary can be 2x the rate. Use sliding window.
- **The "no Retry-After" gotcha.** The client doesn't
  know when to retry. Always include `Retry-After`.
- **The "fail closed" gotcha.** A down rate limiter that
  blocks all users is a bug. Fail open.
- **The "no whitelist" gotcha.** Internal services need
  to bypass.
- **The "same limit for all" anti-pattern.** Different
  users need different limits.

## Related
- `rate-limiting-strategies.md`
- `api-rate-limit-by-key.md`
- `api-rate-limiting-detail.md`
- `feature-gating-implementation.md`
- `feature-resilience-patterns.md`
