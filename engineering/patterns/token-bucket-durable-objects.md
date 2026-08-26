# Token Bucket Rate Limiter with Durable Objects (Per-User, Sub-Millisecond)

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A public API receives bursts of traffic from individual users that overwhelm downstream services. A simple counter-per-minute stored in KV is too coarse-grained (60-second windows allow front-loading) and suffers from cold-read latency. You need sub-millisecond, per-user rate limiting that smooths bursts while allowing short peaks, without sacrificing accuracy across distributed Worker instances.

## Context

The **token bucket** algorithm grants each user a bucket of `capacity` tokens that refills at a constant `refillRate` (tokens per second). Each request consumes one token. If the bucket is empty the request is rejected with `429 Too Many Requests`. Compared to a fixed-window counter, token buckets allow short bursts up to `capacity` without penalising users who consistently stay under the average rate.

Cloudflare **Durable Objects** are the right primitive: each user's bucket lives in a single DO instance with serialised access — no race conditions, no compare-and-swap loops, and storage reads are local (in-memory cache within the DO). Round-trip from a Worker to a co-located DO is typically < 1 ms.

```
  Worker A ──┐
  Worker B ──┼──► UserRateLimiter DO (user-123)  ◄─── single writer, fast
  Worker C ──┘         │
                        └── DO Storage (refills lazily on each check)
```

## Section 1 — Durable Object Implementation

```typescript
// rate-limiter.do.ts

export interface TokenBucketState {
  tokens:         number;
  lastRefillTime: number; // epoch ms
}

export interface RateLimitRequest {
  consume: number; // how many tokens to take (usually 1)
}

export interface RateLimitResponse {
  allowed:         boolean;
  remaining:       number;
  resetAfterMs:    number; // ms until at least 1 token is available
  retryAfterMs:    number; // same, for Retry-After header
}

const CAPACITY    = 60;  // burst limit
const REFILL_RATE = 10;  // tokens per second (10 req/s sustained)

export class UserRateLimiter implements DurableObject {
  private state:   DurableObjectState;
  private bucket:  TokenBucketState | null = null;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    if (request.method !== 'POST') {
      return Response.json({ error: 'POST required' }, { status: 405 });
    }

    const body = await request.json<RateLimitRequest>();
    const consume = body.consume ?? 1;

    // Load bucket from storage (only on first call; after that it's in memory)
    if (!this.bucket) {
      this.bucket = await this.state.storage.get<TokenBucketState>('bucket') ?? {
        tokens:         CAPACITY,
        lastRefillTime: Date.now(),
      };
    }

    const result = this.checkAndConsume(this.bucket, consume);

    // Persist updated bucket state asynchronously
    // (alarm-based persistence avoids a storage write on every request)
    await this.state.storage.put('bucket', this.bucket);

    return Response.json(result);
  }

  private checkAndConsume(bucket: TokenBucketState, consume: number): RateLimitResponse {
    const now        = Date.now();
    const elapsed    = (now - bucket.lastRefillTime) / 1000; // seconds
    const refilled   = elapsed * REFILL_RATE;

    // Refill tokens (cap at capacity)
    bucket.tokens         = Math.min(CAPACITY, bucket.tokens + refilled);
    bucket.lastRefillTime = now;

    if (bucket.tokens >= consume) {
      bucket.tokens -= consume;
      return {
        allowed:      true,
        remaining:    Math.floor(bucket.tokens),
        resetAfterMs: 0,
        retryAfterMs: 0,
      };
    }

    // Not enough tokens — compute how long until 1 token is available
    const deficit      = consume - bucket.tokens;
    const waitSeconds  = deficit / REFILL_RATE;
    const waitMs       = Math.ceil(waitSeconds * 1000);

    return {
      allowed:      false,
      remaining:    0,
      resetAfterMs: waitMs,
      retryAfterMs: waitMs,
    };
  }

  // Optional: alarm-based cleanup so idle buckets don't linger
  async alarm(): Promise<void> {
    // If no requests for 10 minutes, delete state (it will be recreated on next hit)
    const bucket = await this.state.storage.get<TokenBucketState>('bucket');
    if (bucket) {
      const idleMs = Date.now() - bucket.lastRefillTime;
      if (idleMs > 10 * 60 * 1000) {
        await this.state.storage.delete('bucket');
      }
    }
  }
}
```

## Section 2 — Worker Integration

```typescript
// worker.ts
export interface Env {
  RATE_LIMITER: DurableObjectNamespace;
}

export { UserRateLimiter } from './rate-limiter.do';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Identify the user — prefer a verified JWT sub; fall back to IP
    const userId = getUserId(request) ?? getClientIP(request);
    if (!userId) {
      return Response.json({ error: 'Cannot identify client' }, { status: 400 });
    }

    // Each unique userId maps to its own DO instance
    const doId   = env.RATE_LIMITER.idFromName(userId);
    const limiter = env.RATE_LIMITER.get(doId);

    const limitResp = await limiter.fetch('https://do/check', {
      method: 'POST',
      body:   JSON.stringify({ consume: 1 }),
      headers: { 'Content-Type': 'application/json' },
    });
    const limit = await limitResp.json<import('./rate-limiter.do').RateLimitResponse>();

    if (!limit.allowed) {
      return new Response('Too Many Requests', {
        status: 429,
        headers: {
          'Retry-After':               String(Math.ceil(limit.retryAfterMs / 1000)),
          'X-RateLimit-Limit':         String(60),
          'X-RateLimit-Remaining':     '0',
          'X-RateLimit-Reset-After':   String(limit.resetAfterMs),
        },
      });
    }

    // Proceed to actual handler
    const response = await handleRequest(request, env, ctx);

    return addRateLimitHeaders(response, limit);
  },
};

function addRateLimitHeaders(resp: Response, limit: import('./rate-limiter.do').RateLimitResponse): Response {
  const headers = new Headers(resp.headers);
  headers.set('X-RateLimit-Limit',     '60');
  headers.set('X-RateLimit-Remaining', String(limit.remaining));
  return new Response(resp.body, { status: resp.status, headers });
}

function getUserId(request: Request): string | null {
  // In production, verify a JWT and return the `sub` claim
  return request.headers.get('X-User-Id');
}

function getClientIP(request: Request): string | null {
  return request.headers.get('CF-Connecting-IP');
}

async function handleRequest(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
  return Response.json({ message: 'Hello, world!' });
}
```

## Section 3 — wrangler.toml Configuration

```toml
# wrangler.toml
name = "my-api"
main = "src/worker.ts"
compatibility_date = "2024-09-23"

[[durable_objects.bindings]]
name       = "RATE_LIMITER"
class_name = "UserRateLimiter"

[[migrations]]
tag              = "v1"
new_classes      = ["UserRateLimiter"]
```

## Section 4 — Advanced: Per-Route Quotas

Different endpoints may have different costs. Pass a `consume` weight per endpoint:

```typescript
// cost-map.ts
export const ROUTE_COSTS: Record<string, number> = {
  '/api/search':     5,  // expensive — costs 5 tokens
  '/api/export':    20,  // very expensive
  '/api/ping':       0,  // free (health check)
  // default: 1 for all other routes
};

// In the worker:
const url    = new URL(request.url);
const cost   = ROUTE_COSTS[url.pathname] ?? 1;

const limitResp = await limiter.fetch('https://do/check', {
  method: 'POST',
  body:   JSON.stringify({ consume: cost }),
  headers: { 'Content-Type': 'application/json' },
});
```

For truly fine-grained per-tier limits, derive the bucket config from the user's subscription tier stored in D1:

```typescript
// In the DO fetch handler — load tier config on first request
const tierConfig = await loadTierConfig(userId); // reads D1 once, caches in DO memory
const CAPACITY    = tierConfig.burstLimit;
const REFILL_RATE = tierConfig.sustainedRps;
```

## Anti-patterns

**Using KV for token bucket state.** KV is eventually consistent with ~60 ms read latency. Two Workers can both read `tokens=5`, both decrement to 4, and both write 4 — the counter race makes limits meaningless under load. Use Durable Objects for serialised access.

**Blocking the DO on every storage write.** `await storage.put()` on every request doubles latency. Instead, update in-memory state immediately and use `ctx.waitUntil(storage.put(...))` for background persistence, accepting that a DO crash can lose the last tick of token accounting.

**Storing per-IP state without rate-limiting the DO namespace.** A DDoS that sends from millions of IPs creates millions of DO instances. Add a coarse-grained IP block at the Cloudflare WAF level before the Worker for protection against this amplification.

**Missing alarm-based eviction.** Idle DO instances with stale storage waste quota. Register an alarm in the constructor to clean up after inactivity.

## Gotchas

- **DO name must be stable across renames.** `idFromName(userId)` is deterministic but permanent — renaming the DO class deletes all existing instances. Use migrations carefully.
- **DO round-trip adds ~0.5–2 ms** within the same region. If the Worker and DO are in different regions (user in Tokyo, DO in us-east), latency rises to 100+ ms. Use `locationHint` on `get()` to colocate: `env.RATE_LIMITER.get(doId, { locationHint: 'apac' })`.
- **`Date.now()` inside a DO** is real wall-clock time, not simulated. Ensure the refill math uses floating-point division; integer division causes token accumulation gaps at sub-second intervals.
- **Concurrent requests to the same DO are queued**, not parallelised. This is the correct behaviour for serialisation but means a DO under very high per-user load (> 1000 req/s from one user) becomes a bottleneck. At that scale, shard by `userId + Math.floor(Date.now() / 100)` and aggregate across shards.

## Verification

```bash
# Deploy
wrangler deploy

# Burst beyond capacity (should get 429 after 60 requests)
for i in $(seq 1 70); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-User-Id: test-user-1" \
    https://my-api.example.com/api/ping)
  echo "Request $i: $STATUS"
done

# Check Retry-After header on 429
curl -I -H "X-User-Id: test-user-1" https://my-api.example.com/api/search
```

Unit test with Miniflare / Vitest:

```typescript
import { describe, it, expect } from 'vitest';
import { UserRateLimiter } from '../src/rate-limiter.do';

describe('TokenBucket', () => {
  it('allows up to capacity requests in a burst', async () => {
    // Uses Miniflare DurableObject test harness
    const env = getMiniflareBindings();
    for (let i = 0; i < 60; i++) {
      const res = await callLimiter(env, 'user-1', 1);
      expect(res.allowed).toBe(true);
    }
    const over = await callLimiter(env, 'user-1', 1);
    expect(over.allowed).toBe(false);
  });
});
```

## Related

- `kv-rate-limiting.md` — simpler KV-based fixed-window limiter (lower fidelity)
- `api-rate-limiting-detail.md` — broader rate-limiting strategies
- `per-tenant-durable-object.md` — general DO per-entity pattern
- `feature-cookbook-realtime-rate-limiting.md` — real-time adjustments

## Sources

- Cloudflare Durable Objects docs — developers.cloudflare.com/durable-objects/
- Token bucket algorithm — en.wikipedia.org/wiki/Token_bucket
- Cloudflare blog, "Using Durable Objects for Rate Limiting" — blog.cloudflare.com
- "Designing Rate Limiters", Stripe Engineering Blog — stripe.com/blog/rate-limiters
