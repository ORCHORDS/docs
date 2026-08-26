# Token Bucket Rate Limiter with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker endpoint is being hammered by bursts of traffic — scrapers, retry storms, or abusive API consumers. A simple counter reset every minute is too blunt: it allows all requests in the first second and then blocks the rest. You need a token bucket that smooths out burst traffic while still allowing short legitimate bursts up to a configured capacity.

---

## Context

Cloudflare Workers are stateless by design, so rate-limit state cannot live in module-level variables. Durable Objects give you a single-writer, strongly consistent key-value store scoped to one logical entity — perfect for per-user or per-IP rate limit counters. Each user gets their own DO instance addressed by `idFromName(identifier)`, so buckets never contend with each other.

The token bucket algorithm models a bucket that holds up to `capacity` tokens. Tokens refill at a constant rate (tokens/second). Each request consumes one token. If the bucket is empty, the request is rejected with `429 Too Many Requests`.

---

## Solution

```typescript
// src/rate-limiter-do.ts
import { DurableObject } from 'cloudflare:workers';

export interface Env {
  RATE_LIMITER: DurableObjectNamespace;
  RATE_LIMIT_CAPACITY: string;   // e.g. "60"
  RATE_LIMIT_REFILL_RATE: string; // tokens per second, e.g. "1"
}

interface BucketState {
  tokens: number;
  lastRefillAt: number; // Unix ms
}

export class RateLimiterDO extends DurableObject {
  private capacity: number;
  private refillRate: number; // tokens per second

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.capacity = Number(env.RATE_LIMIT_CAPACITY ?? 60);
    this.refillRate = Number(env.RATE_LIMIT_REFILL_RATE ?? 1);
  }

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();

    // Transactional read-modify-write to prevent lost updates
    const result = await this.ctx.storage.transaction(async (txn) => {
      const stored = await txn.get<BucketState>('bucket');

      let tokens: number;
      let lastRefillAt: number;

      if (!stored) {
        // First request — start with a full bucket
        tokens = this.capacity;
        lastRefillAt = now;
      } else {
        tokens = stored.tokens;
        lastRefillAt = stored.lastRefillAt;
      }

      // Refill on read: calculate tokens earned since last refill
      const elapsedSeconds = (now - lastRefillAt) / 1000;
      const refilled = Math.floor(elapsedSeconds * this.refillRate);

      if (refilled > 0) {
        tokens = Math.min(this.capacity, tokens + refilled);
        lastRefillAt = now;
      }

      const allowed = tokens > 0;

      if (allowed) {
        tokens -= 1;
      }

      await txn.put<BucketState>('bucket', { tokens, lastRefillAt });

      // Calculate reset time: seconds until at least one token is available
      const tokensNeeded = allowed ? 0 : 1;
      const secondsUntilReset =
        tokensNeeded === 0
          ? 0
          : Math.ceil((tokensNeeded - (tokens % this.refillRate)) / this.refillRate);

      return { allowed, tokens, resetAt: Math.floor(now / 1000) + secondsUntilReset };
    });

    const headers = new Headers({
      'X-RateLimit-Limit': String(this.capacity),
      'X-RateLimit-Remaining': String(result.tokens),
      'X-RateLimit-Reset': String(result.resetAt),
      'Content-Type': 'application/json',
    });

    if (!result.allowed) {
      headers.set('Retry-After', String(result.resetAt - Math.floor(Date.now() / 1000)));
      return new Response(JSON.stringify({ error: 'rate_limit_exceeded' }), {
        status: 429,
        headers,
      });
    }

    return new Response(JSON.stringify({ allowed: true, remaining: result.tokens }), {
      status: 200,
      headers,
    });
  }
}

// src/worker.ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const identifier = getClientIdentifier(request);
    const doId = env.RATE_LIMITER.idFromName(identifier);
    const stub = env.RATE_LIMITER.get(doId);

    // Delegate rate-limit check to the DO
    const limiterResponse = await stub.fetch(request);

    if (limiterResponse.status === 429) {
      return limiterResponse; // Propagate rate limit headers and body
    }

    // Rate limit headers are forwarded to the actual response
    const rlHeaders = {
      'X-RateLimit-Limit': limiterResponse.headers.get('X-RateLimit-Limit') ?? '',
      'X-RateLimit-Remaining': limiterResponse.headers.get('X-RateLimit-Remaining') ?? '',
      'X-RateLimit-Reset': limiterResponse.headers.get('X-RateLimit-Reset') ?? '',
    };

    // --- Handle the actual request here ---
    const body = { message: 'Hello from Workers', identifier };

    return new Response(JSON.stringify(body), {
      headers: { 'Content-Type': 'application/json', ...rlHeaders },
    });
  },
};

/**
 * Derive a stable client identifier from the request.
 * Priority: Authorization bearer token > CF-Connecting-IP.
 * The identifier is hashed so raw tokens are never stored.
 */
async function getClientIdentifier(request: Request): Promise<string> {
  const auth = request.headers.get('Authorization') ?? '';
  const bearer = auth.startsWith('Bearer ') ? auth.slice(7) : null;
  const raw = bearer ?? request.headers.get('CF-Connecting-IP') ?? 'anonymous';

  const encoded = new TextEncoder().encode(raw);
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

```jsonc
// wrangler.toml (relevant excerpt)
[[durable_objects.bindings]]
name = "RATE_LIMITER"
class_name = "RateLimiterDO"

[[migrations]]
tag = "v1"
new_classes = ["RateLimiterDO"]

[vars]
RATE_LIMIT_CAPACITY = "60"
RATE_LIMIT_REFILL_RATE = "1"
```

---

## Implementation Details

**Refill-on-read** avoids scheduling alarm callbacks for every bucket. Instead, the elapsed time since the last write is used to compute how many tokens have been earned. This is O(1) and requires no background work.

**Transactional storage** (`ctx.storage.transaction`) ensures that concurrent requests hitting the same DO instance cannot both read `tokens = 1` and both succeed — the second write will see the updated state from the first.

**Per-user DO instances** are addressed via `env.RATE_LIMITER.idFromName(identifier)`. The identifier is a SHA-256 hash of the bearer token or IP, so raw credentials are never stored in DO names (which appear in logs).

**Rate limit headers** follow the IETF `RateLimit` draft (headers-08):
- `X-RateLimit-Limit` — bucket capacity
- `X-RateLimit-Remaining` — tokens left after this request
- `X-RateLimit-Reset` — Unix timestamp when the bucket will be full again
- `Retry-After` — seconds until at least one token is available (only on 429)

---

## Anti-patterns

- **Storing rate limit state in a KV namespace.** KV has eventual consistency; two edge nodes can both read the same stale token count and both allow a request that should have been rejected.
- **Using module-level variables.** Workers can run on multiple isolates simultaneously; module-level state is not shared between them.
- **Resetting `lastRefillAt` on every request.** This effectively pauses token accumulation while traffic is flowing, making the bucket starve under sustained load. Only update `lastRefillAt` when you actually add tokens.
- **Using wall-clock `Date.now()` inside the transaction for the reset header.** Compute the reset timestamp from `lastRefillAt + refillPeriod`, not from the current time inside the transaction, to avoid clock skew in the header value.

---

## Gotchas

- **DO warm-up latency.** The first request to a newly created DO instance incurs a cold-start penalty (~5–50 ms). If your endpoint is latency-sensitive, pre-warm DOs by sending a no-op request during deploy.
- **DO location.** By default, Cloudflare places the DO in the region closest to the first request. Subsequent requests from different regions are routed to that one location. For global APIs with geographically distributed clients, add a `locationHint` to `idFromName` calls or use the `locationHint` option on `get()`.
- **Capacity vs. refill rate units.** `refillRate` is tokens per second. Setting `capacity = 60` and `refillRate = 1` gives 1 req/s sustained with a burst of 60. Setting `refillRate = 60` and `capacity = 60` gives 60 req/s sustained — a very different behaviour.
- **Integer truncation.** `Math.floor(elapsedSeconds * refillRate)` truncates fractional tokens. Sub-second precision is lost. This is intentional — it prevents fractional token accumulation drift over time.

---

## Verification

```bash
# Smoke test: fire 65 requests and watch for 429s
for i in $(seq 1 65); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer test-user-1" \
    https://your-worker.your-subdomain.workers.dev/api/resource)
  echo "Request $i: $STATUS"
done

# Inspect rate limit headers on a single request
curl -si -H "Authorization: Bearer test-user-1" \
  https://your-worker.your-subdomain.workers.dev/api/resource \
  | grep -i 'x-ratelimit\|retry-after'
```

Expected output: requests 1–60 return `200`, requests 61–65 return `429` with `Retry-After` set. After waiting `Retry-After` seconds, the next request returns `200`.

---

## Related

- `workers-read-through-cache-pattern.md` — caching layer to reduce load before rate limiting
- `workers-compensating-transaction-pattern.md` — transactional patterns with DOs
- Cloudflare Docs: [Durable Objects](https://developers.cloudflare.com/durable-objects/)
- Cloudflare Docs: [Durable Object Storage API](https://developers.cloudflare.com/durable-objects/api/storage-api/)

---

## Sources

- Token Bucket algorithm — Wikipedia: https://en.wikipedia.org/wiki/Token_bucket
- IETF RateLimit Headers draft: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- Cloudflare Workers Runtime API — `crypto.subtle`: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
