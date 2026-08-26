# feature-cookbook-realtime-rate-limiting

**Issue:** Rate limiting — per-user, per-IP, per-endpoint
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user reports slow responses. You look at the logs.
A single IP is making 1000 requests/sec. The DB is
overwhelmed. The other users are slow. You wish you'd
rate-limited.

## Root cause
**Without rate limits, abuse kills the API.** Use rate
limiting.

**Source:** IETF — RateLimit:
https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/

## Rate limiting algorithms

### Fixed window
- **How:** Allow N requests per fixed time window
- **Pros:** Simple
- **Cons:** Bursts at the edge

### Sliding window
- **How:** Allow N requests in the last N seconds
- **Pros:** Smoother
- **Cons:** More complex

### Token bucket
- **How:** Refill N tokens/sec, each request takes 1
- **Pros:** Allows bursts
- **Cons:** More complex

### Leaky bucket
- **How:** Process at a fixed rate
- **Pros:** Smooth output
- **Cons:** Higher latency

For most apps, **sliding window** is the right balance.

## The "per-user" pattern

For per-user:
```ts
async function isRateLimited(userId: string, env: Env): Promise<boolean> {
  const limit = 100;
  const window = 60_000;
  const now = Date.now();
  const key = `rate:${userId}`;

  const timestamps = (await env.KV!.get<number[]>(key, 'json')) ?? [];
  const recent = timestamps.filter(t => t > now - window);

  if (recent.length >= limit) {
    return true;
  }

  recent.push(now);
  await env.KV!.put(key, JSON.stringify(recent), { expirationTtl: 60 });
  return false;
}
```

The user is rate-limited.

## The "per-IP" pattern

For per-IP:
```ts
async function isRateLimitedByIP(request: Request, env: Env): Promise<boolean> {
  const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
  const limit = 100;
  const window = 60_000;

  return isRateLimited(`ip:${ip}`, env);
}
```

The IP is rate-limited.

## The "per-endpoint" pattern

For per-endpoint:
```ts
async function isRateLimitedPerEndpoint(userId: string, endpoint: string, env: Env): Promise<boolean> {
  const limit = 50;  // Lower for expensive endpoints
  return isRateLimited(`${userId}:${endpoint}`, env);
}
```

The endpoint is rate-limited.

## The "tier-based" pattern

For tier-based:
```ts
const limits = {
  free: 100,
  pro: 1000,
  enterprise: 10000,
};

async function isRateLimitedForUser(user: User, env: Env): Promise<boolean> {
  const limit = limits[user.tier] ?? 100;
  const key = `rate:${user.id}`;
  // ... check
}
```

The tier determines the limit.

## The "rate limit headers" pattern

For headers (IETF):
```ts
response.headers.set('RateLimit-Limit', '100');
response.headers.set('RateLimit-Remaining', '50');
response.headers.set('RateLimit-Reset', '60');
```

**Source:** IETF RateLimit:
https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/

## The "rate limit middleware" pattern

For middleware:
```ts
async function withRateLimit(
  request: Request,
  env: Env,
  handler: (req: Request) => Promise<Response>,
): Promise<Response> {
  const userId = await getUserId(request, env);
  if (!userId) return handler(request);

  if (await isRateLimited(userId, env)) {
    return new Response('Too Many Requests', {
      status: 429,
      headers: {
        'RateLimit-Limit': '100',
        'RateLimit-Remaining': '0',
        'Retry-After': '60',
      },
    });
  }

  return handler(request);
}
```

The middleware handles rate limiting.

## The "rate limit observability" pattern

For observability:
```ts
metrics.increment('rate_limit.requests_total', { tier: user.tier, allowed: 'true' });
metrics.increment('rate_limit.requests_total', { tier: user.tier, allowed: 'false' });
```

The rate limit is monitored.

## The "rate limit bypass" pattern

For bypass:
```ts
function isBypassed(request: Request): boolean {
  return ['/health', '/ready'].includes(new URL(request.url).pathname);
}
```

Health checks bypass.

## The "rate limit anti-pattern" anti-patterns

### 1. No rate limit
- **Issue:** Abuse
- **Fix:** Use rate limit

### 2. Per-user only
- **Issue:** Anonymous abuse
- **Fix:** Per-IP for unauth

### 3. No headers
- **Issue:** Client doesn't know
- **Fix:** RateLimit headers

### 4. Same for all endpoints
- **Issue:** Expensive endpoints abuse
- **Fix:** Per-endpoint

## Verification
- **Test:** Rate limit works
- **Test:** Headers set
- **Live:** Rate limit metrics
- **Audit:** Quarterly review

## Gotchas
- **The "no rate limit" anti-pattern.** Use one.
- **The "no headers" anti-pattern.** IETF headers.

## Related
- `api-rate-limit-by-key.md`
- `api-rate-limiting-detail.md`
- `feature-cookbook-rate-limiting-detail.md`
- IETF RateLimit: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
