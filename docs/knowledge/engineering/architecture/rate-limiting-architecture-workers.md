# rate-limiting-architecture-workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

API endpoints on Cloudflare Workers get scraped or abused at scale.
A naive per-Worker counter resets on isolate recycling—limits are
ineffective. Mobile clients behind carrier-grade NAT (CGNAT) share
one public IP with thousands of users; IP-only rate limiting bans
legitimate users. Browser-only fingerprinting breaks on native mobile
apps. High-traffic endpoints hit Cloudflare's built-in rate limiter
but the limit has no notion of authenticated user quotas.

## Context

Effective rate limiting on Workers requires three complementary
layers. Layer 1 is the Cloudflare-managed network-level rate
limiter—cheap, evaluated before JavaScript runs. Layer 2 uses Workers
KV for per-user sliding-window counters persisted across isolates.
Layer 3 uses a Durable Object for strict per-resource counters needing
strong consistency (payment endpoints, OTP attempts). The client type
(mobile app vs browser vs API key) determines which identifier to
use as the rate-limit key.

## 1. Layered Architecture Overview

```
Request
  │
  ▼
┌─────────────────────────────────────────┐
│  Layer 1: CF Managed Rate Limiting      │
│  • Per-IP or per-fingerprint            │
│  • Evaluated in CF data plane           │
│  • ~0 ms overhead, no JS               │
│  • Config: wrangler.toml rule           │
└────────────────┬────────────────────────┘
                 │ passed
                 ▼
┌─────────────────────────────────────────┐
│  Layer 2: Workers KV Sliding Window     │
│  • Per authenticated user (JWT sub)     │
│  • Eventually consistent (~60 ms lag)  │
│  • Good for: standard API quotas        │
└────────────────┬────────────────────────┘
                 │ passed
                 ▼
┌─────────────────────────────────────────┐
│  Layer 3: Durable Object Counter        │
│  • Strict serialized counter            │
│  • Per-resource (OTP, payment, invite)  │
│  • Strong consistency, ~5 ms overhead   │
└────────────────┬────────────────────────┘
                 │ passed
                 ▼
              Handler
```

## 2. Layer 1 — Cloudflare Managed Rate Limiting

Configure in `wrangler.toml` (no JavaScript required):

```toml
[[unsafe.bindings]]
name = "RATE_LIMITER"
type = "ratelimit"
namespace_id = "1"
simple = { limit = 100, period = 60 }
```

Use in Worker:

```typescript
// Check before any auth or logic
const { success } = await env.RATE_LIMITER.limit({
  key: getIpKey(request),
});
if (!success) {
  return new Response(JSON.stringify({ error: "rate_limited" }), {
    status: 429,
    headers: {
      "Content-Type": "application/json",
      "Retry-After": "60",
    },
  });
}
```

Key selection by client type:

```
Client type          Key                       Rationale
─────────────────────────────────────────────────────────────────
Mobile (authed)      JWT `sub` (user ID)       Avoids CGNAT collision
Mobile (anon)        IP + UA hash (16 chars)   Light fingerprint
Browser (authed)     JWT `sub`                 Same as mobile authed
Browser (anon)       CF-connecting-ip          Acceptable for browser
API key client       API key prefix (8 chars)  Per-key quota
```

## 3. Layer 2 — KV Sliding Window Counter

Workers KV is eventually consistent; counts may be slightly stale
under write propagation delay (~60 s globally). Acceptable for
API quota enforcement where soft over-limit by a few requests is
tolerable. Not acceptable for OTP or payment rate limits.

```typescript
async function checkKvRateLimit(
  userId: string,
  limit: number,
  windowSec: number,
  env: Env
): Promise<{ allowed: boolean; remaining: number }> {
  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - windowSec;
  const key = `rl:${userId}:${Math.floor(now / windowSec)}`;

  const raw = await env.RATE_KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= limit) {
    return { allowed: false, remaining: 0 };
  }

  // Increment; TTL = 2x window to survive propagation lag
  await env.RATE_KV.put(key, String(count + 1), {
    expirationTtl: windowSec * 2,
  });

  return { allowed: true, remaining: limit - count - 1 };
}
```

Response headers that mobile clients should respect:

```typescript
headers.set("X-RateLimit-Limit", String(limit));
headers.set("X-RateLimit-Remaining", String(result.remaining));
headers.set("X-RateLimit-Reset", String(windowResetEpoch));
```

## 4. Layer 3 — Durable Object Strict Counter

Use for endpoints where over-limit by even 1 request causes harm
(OTP brute force, payment submission, password reset).

```typescript
export class StrictCounterDO implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    const { limit, windowMs } = await req.json<CounterParams>();
    const now = Date.now();

    await this.state.storage.transaction(async (txn) => {
      const windowStart = (await txn.get<number>("windowStart")) ?? now;
      let count = (await txn.get<number>("count")) ?? 0;

      // Reset if window has passed
      if (now - windowStart > windowMs) {
        count = 0;
        await txn.put("windowStart", now);
      }

      await txn.put("count", count + 1);
      // Attach result to state for reading after transaction
      (this as any)._lastCount = count + 1;
    });

    const count = (this as any)._lastCount as number;
    const allowed = count <= limit;
    return new Response(JSON.stringify({ allowed, count }), {
      status: allowed ? 200 : 429,
    });
  }
}
```

Worker routing to the DO by resource ID:

```typescript
async function checkDoRateLimit(
  resourceId: string,
  limit: number,
  windowMs: number,
  env: Env
): Promise<boolean> {
  const id = env.STRICT_COUNTER.idFromName(resourceId);
  const stub = env.STRICT_COUNTER.get(id);
  const res = await stub.fetch("https://internal/check", {
    method: "POST",
    body: JSON.stringify({ limit, windowMs }),
  });
  const { allowed } = await res.json<{ allowed: boolean }>();
  return allowed;
}
```

## 5. Mobile App vs Browser Client Handling

Mobile apps behind CGNAT share IPs; IP-only limits create false
positives. Strategies by authentication state:

```
State          Identifier strategy
─────────────────────────────────────────────────────────────────
Authenticated  JWT `sub` — use for all layers
Anonymous      Composite: ip + truncated user-agent hash
               ip = CF-Connecting-IP header (Cloudflare strips XFF)
               ua_hash = first 16 chars of SHA-256(User-Agent)

Anonymous mobile quota should be 3-5× higher than authenticated
to absorb CGNAT aggregation before auth is complete.
```

Computing the anon fingerprint:

```typescript
async function anonKey(req: Request): Promise<string> {
  const ip = req.headers.get("CF-Connecting-IP") ?? "unknown";
  const ua = req.headers.get("User-Agent") ?? "";
  const raw = new TextEncoder().encode(`${ip}|${ua}`);
  const hash = await crypto.subtle.digest("SHA-256", raw);
  const hex = [...new Uint8Array(hash)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
  return `anon:${hex}`;
}
```

## Anti-Patterns

- **In-memory counters in the Worker** — reset per isolate restart;
  never reflects true global rate.
- **Using KV for OTP or payment rate limits** — eventual consistency
  allows burst over-limit; use DO for strict resources.
- **Banning by raw IP for mobile** — CGNAT puts thousands of users
  on one IP; will cause support escalations.
- **Not returning Retry-After** — mobile app retry loops without
  backoff will hammer the endpoint even harder.
- **One rate limit rule for all endpoints** — public endpoints need
  much looser limits than admin or payment endpoints.

## Gotchas

- `CF-Connecting-IP` is always the real client IP behind Cloudflare's
  proxy; `X-Forwarded-For` can be spoofed by the client—never use it.
- The managed Rate Limiting binding counts requests globally across
  all Cloudflare data centers; it is not per-colo.
- KV `put` without `expirationTtl` creates keys that never expire;
  KV quota exhaustion will silently start returning stale or missing
  values for new keys.
- DO storage transactions are serialized; a busy OTP counter DO will
  queue requests; set a 2 s timeout on DO fetch calls.
- Cloudflare's managed rate limiter fires a 429 before your Worker
  JS runs; you cannot customize the response body at Layer 1.

## Verification

```bash
# Trigger Layer 1 limit (100 req/min in example above)
for i in $(seq 1 110); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    https://your-worker.example.com/api/me
done
# Last ~10 should print 429

# Test Layer 2 KV counter (login with same user)
for i in $(seq 1 55); do
  curl -s -H "Authorization: Bearer $TOKEN" \
    -o /dev/null -w "%{http_code} %header{x-ratelimit-remaining}\n" \
    https://your-worker.example.com/api/data
done
# Should see remaining count decrease, then 429

# Check DO strict counter (OTP endpoint)
for i in $(seq 1 6); do
  curl -s -X POST https://your-worker.example.com/api/otp/verify \
    -d '{"code":"000000"}' -w " → %{http_code}\n"
done
# 6th attempt should be 429 regardless of KV propagation
```

## Related

- `documentation/docs/policies/architecture/workers-do-websocket-architecture.md`
- `documentation/docs/policies/architecture/api-security-architecture.md`
- `documentation/docs/policies/architecture/circuit-breaker-design.md`
- `documentation/docs/policies/architecture/feature-flag-cloudflare-workers-kv.md`
- `documentation/docs/policies/architecture/idempotency-design.md`

## Source URLs

- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/fundamentals/reference/http-request-headers/
