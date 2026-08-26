# api-rate-limiting-detail

**Issue:** Rate limiting — algorithms, dimensions, response
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user is hitting your API at 1000 req/sec. The DB is
overwhelmed. Other users see errors. You block the IP. The
user is using a legit app with a bug. The bug is fixed
but the IP is still blocked.

## Root cause
**Without rate limiting, one user can DoS the system.**

**Source:** Stripe rate limiting:
https://stripe.com/docs/rate-limits

> "Rate limits protect your account from being overwhelmed
> by too many requests."

## The 4 main algorithms

### 1. Fixed window
- **What:** Count requests in a fixed window (e.g. 1 min)
- **Pros:** Simple
- **Cons:** Burst at window boundary (2x rate possible)

```ts
const key = `rl:${userId}:${Math.floor(Date.now() / 60000)}`;
const count = await env.KV.get(key);
if (count && parseInt(count) > limit) {
  return new Response('Rate limited', { status: 429 });
}
await env.KV.put(key, String((parseInt(count ?? '0') + 1)), { expirationTtl: 60 });
```

### 2. Sliding window
- **What:** Count requests in a sliding window (last 60s)
- **Pros:** More accurate
- **Cons:** More complex

```ts
// Use a DO or Redis for sliding window
class SlidingWindow {
  private requests: number[] = [];

  isAllowed(limit: number, windowMs: number): boolean {
    const now = Date.now();
    this.requests = this.requests.filter(t => now - t < windowMs);
    if (this.requests.length >= limit) return false;
    this.requests.push(now);
    return true;
  }
}
```

### 3. Token bucket
- **What:** Bucket holds N tokens; each request consumes 1
- **Pros:** Allows bursts
- **Cons:** More complex

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

  consume(): boolean {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(this.capacity, this.tokens + elapsed * this.refillRate);
    this.lastRefill = now;

    if (this.tokens < 1) return false;
    this.tokens -= 1;
    return true;
  }
}
```

### 4. Leaky bucket
- **What:** Bucket processes at a constant rate
- **Pros:** Smooths bursts
- **Cons:** Slower than token bucket

```ts
// Similar to token bucket, but processes at a fixed rate
```

## The "dimension" choice

Rate limit by:
- **IP:** Protect against bots
- **User ID:** Protect against user abuse
- **Tenant ID:** Protect against tenant abuse
- **API key:** Protect against key abuse
- **Endpoint:** Protect expensive endpoints

Combine:
- **Per user:** 100 req/sec
- **Per IP:** 1000 req/sec
- **Per user per endpoint:** 10 req/sec on /api/search

## The "per-user" pattern

```ts
async function checkRateLimit(userId: string, env: Env, limit = 100): Promise<{ allowed: boolean; remaining: number; resetAt: number }> {
  const id = env.RATE_LIMIT.idFromName(userId);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate-limit/check', {
    method: 'POST',
    body: JSON.stringify({ limit }),
  });
  return response.json();
}
```

The DO holds the per-user state.

## The "per-IP" pattern

```ts
async function checkRateLimitIP(ip: string, env: Env, limit = 1000): Promise<{ allowed: boolean }> {
  // Use CF's rate limiting rules
  // Or use a DO with the IP as the name
  const id = env.RATE_LIMIT.idFromName(`ip:${ip}`);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate-limit/check', {
    method: 'POST',
    body: JSON.stringify({ limit }),
  });
  return response.json();
}
```

## The "per-tenant" pattern

```ts
async function checkRateLimitTenant(tenantId: string, env: Env, limit = 10000): Promise<{ allowed: boolean }> {
  // Per-tenant: 10x per-user
  const id = env.RATE_LIMIT.idFromName(`tenant:${tenantId}`);
  // ...
}
```

## The "tiered" pattern

Different limits per plan:
```ts
const PLAN_LIMITS = {
  free: 100,
  pro: 1000,
  enterprise: 10000,
};

const limit = PLAN_LIMITS[ctx.user.plan] ?? PLAN_LIMITS.free;
const { allowed, remaining } = await checkRateLimit(ctx.user.id, env, limit);
```

## The "response" pattern

For a rate-limited response:
```ts
if (!allowed) {
  return new Response(JSON.stringify({
    type: 'https://example.com/probs/rate-limited',
    title: 'Rate limit exceeded',
    status: 429,
    detail: 'You have exceeded the rate limit',
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

The client knows:
- The limit (`X-RateLimit-Limit`)
- The remaining (`X-RateLimit-Remaining`)
- When to retry (`Retry-After`)

## The "rate limit" header convention

Use the IETF draft:
- `RateLimit-Limit: 100` — the limit
- `RateLimit-Remaining: 50` — the remaining
- `RateLimit-Reset: 60` — seconds until reset

The IETF draft: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/

## The "client" pattern

A polite client respects the rate limit:
```ts
async function fetchWithRateLimit(url: string, options: RequestInit): Promise<Response> {
  const res = await fetch(url, options);

  if (res.status === 429) {
    const retryAfter = parseInt(res.headers.get('Retry-After') ?? '60');
    await sleep(retryAfter * 1000);
    return fetchWithRateLimit(url, options);  // Retry once
  }

  return res;
}
```

The client backs off + retries.

## The "bypass" pattern

For trusted clients (internal services, admins), bypass the
rate limit:
```ts
if (isAdmin(ctx.user) || isInternalService(request)) {
  return next();
}

return checkRateLimit(...);
```

The bypass is logged for audit.

## The "burst" allowance

For some apps, allow bursts:
- 100 req/sec steady-state
- 200 req/sec burst (up to 5 seconds)

The token bucket handles this naturally.

## The "fail open" pattern

If the rate limiter is down, allow the request (fail open):
```ts
try {
  const { allowed } = await checkRateLimit(userId, env);
  if (!allowed) return new Response('Rate limited', { status: 429 });
} catch (err) {
  // Log but allow
  console.error({ msg: 'rate.limit.error', error: String(err) });
}

return next();
```

Failing open is safer than failing closed (which would
block all users).

## The "metrics" pattern

Track rate limit metrics:
```ts
metrics.increment('rate_limit.checks_total', { result: 'allowed' });
metrics.increment('rate_limit.checks_total', { result: 'denied' });

// Per-user
metrics.increment('rate_limit.denied_total', { userId });
```

The metrics show:
- How often users are rate-limited
- Which users are most often limited

## The "user feedback" pattern

For a user hitting the limit, show a clear message:
```ts
return new Response(JSON.stringify({
  type: 'https://example.com/probs/rate-limited',
  title: 'Rate limit exceeded',
  status: 429,
  detail: `You have made ${limit} requests in the last minute. Please wait ${retryAfter} seconds.`,
  code: 'RATE_LIMITED',
}), { status: 429, headers: { 'Retry-After': String(retryAfter) } });
```

The user knows what happened and what to do.

## Verification
- **Test:** Rate limit blocks at the limit
- **Test:** Rate limit allows under the limit
- **Live:** Rate limit metrics are monitored
- **Audit:** Quarterly review of rate limits

## Gotchas
- **The "fixed window boundary" gotcha.** A burst at the
  window boundary can be 2x the rate. Use sliding window
  for accuracy.
- **The "rate limit per user only" gotcha.** A user can
  be one of 1000 tenants; per-tenant rate limit is
  essential.
- **The "rate limit fails closed" gotcha.** A down rate
  limiter that blocks all users is a bug. Fail open.
- **The "rate limit without headers" gotcha.** The client
  doesn't know when to retry. Always set `Retry-After`.
- **The "rate limit for legit users" anti-pattern.** A
  bug in a legit app can cause a user to be rate-limited.
  Have a way to whitelist.
- **The "rate limit is the only protection" anti-pattern.**
  Rate limit protects against volume; it doesn't protect
  against targeted attacks. Use WAF + DDoS protection
  too.

## Related
- `rate-limiting-strategies.md`
- `api-rate-limit-by-key.md`
- `api-design-best-practices.md`
- `feature-gating-implementation.md` (per-plan limits)
- `observability-three-pillars-detail.md`
- IETF rate limit headers: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
- Stripe: https://stripe.com/docs/rate-limits
