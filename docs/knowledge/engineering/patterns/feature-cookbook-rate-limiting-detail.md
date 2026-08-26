# feature-cookbook-rate-limiting-detail

**Issue:** Rate limiting — algorithms, headers, fairness
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your API is being abused. A single user is making 1000
requests/sec. The DB is overwhelmed. The other users
are slow. You wish you'd rate-limited.

## Root cause
**Without rate limits, abuse kills the API.** Use rate
limiting.

**Source:** IETF — RateLimit spec:
https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/

## Rate limiting algorithms

### Fixed window
- **How:** Allow N requests per fixed time window
- **Pros:** Simple
- **Cons:** Bursts at the edge

```ts
const limit = 100;  // 100 requests
const window = 60_000;  // per minute
const counter = await env.KV!.get<number>(`rate:${userId}:${currentMinute}`);
if (counter && counter >= limit) {
  return new Response('Too Many Requests', { status: 429 });
}
await env.KV!.put(`rate:${userId}:${currentMinute}`, String((counter ?? 0) + 1), { expirationTtl: 60 });
```

### Sliding window
- **How:** Allow N requests in the last N seconds
- **Pros:** Smoother
- **Cons:** More complex

```ts
const limit = 100;
const window = 60_000;
const now = Date.now();
const timestamps = await env.KV!.get<number[]>(`rate:${userId}`, 'json') ?? [];
const recent = timestamps.filter(t => t > now - window);
if (recent.length >= limit) {
  return new Response('Too Many Requests', { status: 429 });
}
recent.push(now);
await env.KV!.put(`rate:${userId}`, JSON.stringify(recent), { expirationTtl: 60 });
```

### Token bucket
- **How:** Refill N tokens/sec, each request takes 1
- **Pros:** Allows bursts
- **Cons:** More complex

```ts
const capacity = 100;
const refillRate = 10;  // tokens/sec

let bucket = await env.KV!.get<{ tokens: number; lastRefill: number }>(`bucket:${userId}`, 'json') ?? { tokens: capacity, lastRefill: Date.now() };

const now = Date.now();
const elapsed = (now - bucket.lastRefill) / 1000;
bucket.tokens = Math.min(capacity, bucket.tokens + elapsed * refillRate);
bucket.lastRefill = now;

if (bucket.tokens < 1) {
  await env.KV!.put(`bucket:${userId}`, JSON.stringify(bucket), { expirationTtl: 60 });
  return new Response('Too Many Requests', { status: 429 });
}

bucket.tokens -= 1;
await env.KV!.put(`bucket:${userId}`, JSON.stringify(bucket), { expirationTtl: 60 });
```

### Leaky bucket
- **How:** Process at a fixed rate
- **Pros:** Smooth output
- **Cons:** Higher latency

## The "rate limit headers" pattern

For headers, the IETF draft:
```ts
response.headers.set('RateLimit-Limit', '100');
response.headers.set('RateLimit-Remaining', '50');
response.headers.set('RateLimit-Reset', '60');  // seconds
```

**Source:** IETF RateLimit:
https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/

## The "per-user" pattern

For per-user:
```ts
const key = `rate:${user.id}:${currentMinute}`;
const counter = await env.KV!.get<number>(key);
if (counter && counter >= 100) {
  return new Response('Too Many Requests', { status: 429 });
}
```

Each user has their own counter.

## The "per-IP" pattern

For per-IP:
```ts
const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
const key = `rate:ip:${ip}:${currentMinute}`;
const counter = await env.KV!.get<number>(key);
if (counter && counter >= 100) {
  return new Response('Too Many Requests', { status: 429 });
}
```

Each IP has their own counter.

## The "per-endpoint" pattern

For per-endpoint:
```ts
const endpoint = new URL(request.url).pathname;
const key = `rate:${user.id}:${endpoint}:${currentMinute}`;
const counter = await env.KV!.get<number>(key);
if (counter && counter >= 50) {
  return new Response('Too Many Requests', { status: 429 });
}
```

Each endpoint has its own limit.

## The "tier-based" pattern

For tier-based:
```ts
const limits = {
  free: 100,
  pro: 1000,
  enterprise: 10000,
};

const userLimit = limits[user.tier] ?? 100;
const counter = await env.KV!.get<number>(`rate:${user.id}:${currentMinute}`);
if (counter && counter >= userLimit) {
  return new Response('Too Many Requests', { status: 429 });
}
```

The tier determines the limit.

## The "rate limit middleware" pattern

For middleware, a single function:
```ts
async function withRateLimit(
  request: Request,
  env: Env,
  handler: (req: Request) => Promise<Response>,
): Promise<Response> {
  const userId = await getUserId(request, env);
  if (!userId) return handler(request);

  const key = `rate:${userId}:${currentMinute}`;
  const counter = await env.KV!.get<number>(key);

  if (counter && counter >= 100) {
    return new Response('Too Many Requests', {
      status: 429,
      headers: {
        'RateLimit-Limit': '100',
        'RateLimit-Remaining': '0',
        'RateLimit-Reset': '60',
        'Retry-After': '60',
      },
    });
  }

  await env.KV!.put(key, String((counter ?? 0) + 1), { expirationTtl: 60 });
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

For bypass (e.g. health checks):
```ts
function isBypassed(request: Request): boolean {
  return ['/health', '/ready', '/metrics'].includes(new URL(request.url).pathname);
}

if (isBypassed(request)) return handler(request);
```

The bypass list is explicit.

## The "rate limit anti-pattern" anti-patterns

### 1. No rate limit
- **Issue:** Abuse kills the API
- **Fix:** Use rate limit

### 2. Per-user only (no per-IP)
- **Issue:** Anonymous abuse
- **Fix:** Per-IP for unauthenticated

### 3. Per-IP only (no per-user)
- **Issue:** NAT users share a limit
- **Fix:** Per-user for authenticated

### 4. No headers
- **Issue:** Client doesn't know when to retry
- **Fix:** RateLimit headers

### 5. No monitoring
- **Issue:** Don't know who's hitting the limit
- **Fix:** Monitor

### 6. Same limit for all endpoints
- **Issue:** Expensive endpoints abuse the limit
- **Fix:** Per-endpoint limits

### 7. No bypass
- **Issue:** Health checks are blocked
- **Fix:** Bypass list

## Verification
- **Test:** Rate limit works
- **Test:** Headers are set
- **Test:** Bypass works
- **Live:** Rate limit metrics
- **Audit:** Quarterly review

## Gotchas
- **The "no rate limit" anti-pattern.** Use one.
- **The "no headers" anti-pattern.** IETF headers.
- **The "no monitoring" anti-pattern.** Monitor.

## Related
- `api-rate-limiting-detail.md`
- `api-rate-limit-by-key.md`
- `feature-cookbook-rate-limiting.md`
- `feature-cookbook-caching.md`
- IETF RateLimit: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
