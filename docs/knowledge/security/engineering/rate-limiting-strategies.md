# rate-limiting-strategies

**Issue:** Rate limit choice — token bucket, leaky bucket, fixed window
**Date:** 2026-08-09
**Status:** documented (architectural decision)

## Symptom
You add a `429 Too Many Requests` return to a login endpoint to
prevent brute-force. The first 100 attempts in 1 second are
allowed; the 101st is blocked. But the attacker can fire 100
attempts in the last second of one window + 100 in the first
second of the next window = 200 attempts in 2 seconds (the
"window-boundary burst").

## Root cause
**Fixed window** rate limiting allows the boundary-burst: an
attacker can use 2x the limit by firing at window boundaries.
Other algorithms (token bucket, leaky bucket, sliding window
counter) are more accurate.

**Source:** Cloudflare blog — "Rate Limiting Done Right":
https://blog.cloudflare.com/counting-things-lets-do-it-well/

> "Fixed windows are simple but inaccurate. ... Sliding window
> counters or token buckets are recommended for production."

## Fix
Three algorithms, in order of preference:

### 1. Token bucket (recommended)
Each client has a bucket with `capacity` tokens. Tokens refill at
`rate` per second. Each request consumes 1 token. If the bucket is
empty, the request is rejected.

```ts
// In a Durable Object (per-tenant, per-endpoint):
class RateLimitDO {
  private tokens: number = 60;  // burst capacity
  private lastRefill: number = Date.now();

  async fetch(req: Request): Promise<Response> {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(60, this.tokens + elapsed * 1);  // 1 token/sec
    this.lastRefill = now;
    if (this.tokens < 1) {
      return new Response('Rate limited', { status: 429 });
    }
    this.tokens -= 1;
    return new Response('OK', { status: 200 });
  }
}
```

60 tokens capacity + 1/sec refill = average 1 req/sec, bursts up
to 60 req. Adjust per-endpoint (login: 5 burst / 0.1 refill = 1
attempt per 10 sec; API: 100 burst / 10 refill = 10 req/sec
sustained).

### 2. Sliding window counter
Combines fixed window with a weighted prior window. More accurate
than fixed, less bursty than pure token bucket. Used by Cloudflare
and most CDNs.

```ts
// Per-minute counter: weight previous minute at 0.5, current at 1.0
const current = count[minute(t)];
const previous = count[minute(t) - 1];
const progress = (t - minuteStart) / 60;  // 0..1
const estimated = previous * (1 - progress) + current;
if (estimated > limit) return new Response('Limited', { status: 429 });
```

### 3. Leaky bucket
Like token bucket but the bucket "leaks" at a constant rate (not
refills). Smooths bursts to a steady output. Use when downstream
can only handle a constant rate (e.g. a vendor API with a strict
QPS limit).

## What to limit by

- **Per IP** for unauthenticated endpoints (login, signup, public
  API). Use the IP from `CF-Connecting-IP` header (Cloudflare sets
  this — trust it, not `X-Forwarded-For`).
- **Per user** for authenticated endpoints. Use the session's
  user_id, not the IP (NAT, mobile, VPN).
- **Per tenant** for multi-tenant APIs. A noisy tenant should not
  starve other tenants.
- **Per endpoint + per client** for fine-grained control. Login
  is separate from "list posts" is separate from "create post".

## Verification
- **Test:** `test/ratelimit.test.ts` — fire 200 requests in 2s
  → first 60 succeed, 61+ return 429
- **Live:** Sentry shows 0 "rate-limited legit users" complaints
- **Cloudflare:** WAF managed rules + custom DO-based limits
  layered (defense in depth)

## Gotchas
- **`CF-Connecting-IP` is the trusted IP** behind Cloudflare. Don't
  trust `X-Forwarded-For` (the client can set it).
- **Do NOT count failed auth attempts in the same bucket as
  successful ones.** Otherwise a brute-force attacker can make
  legitimate users get rate-limited by stuffing the wrong password.
- **The 429 response should include `Retry-After`** header with the
  seconds until the client can retry.
- **The DO pattern has a cold-start cost** (~50ms). For chatty
  endpoints, use CF WAF managed rules first (sub-ms), then DO for
  per-user / per-tenant limits.
- **Distributed attacks need distributed defense.** A single DO
  becomes a bottleneck at 100k+ QPS. Layer CF WAF (L7) +
  rate-limit at the edge (L3/L4) for DDoS.

## Related
- `per-tenant-durable-object.md` (the DO pattern)
- Cloudflare WAF: https://developers.cloudflare.com/waf/
- Cloudflare blog: https://blog.cloudflare.com/counting-things-lets-do-it-well/
