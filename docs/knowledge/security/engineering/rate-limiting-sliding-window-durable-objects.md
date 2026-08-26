# Distributed Sliding-Window Rate Limiting with Durable Objects

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Fixed-window counters allow traffic bursts at window boundaries — an attacker can fire N
requests at the end of one window and N more at the start of the next, exceeding the intended
limit by 2N. A sliding-window algorithm eliminates this boundary burst, but requires a shared,
consistent counter that is visible across all Cloudflare edge nodes serving the same client.

## Context

Cloudflare Workers are stateless by design; a naively in-memory counter is per-isolate and
resets on every cold start. Durable Objects provide a single-instance, strongly consistent
storage and actor model accessible from any colo, making them ideal for maintaining sliding-
window state. Each unique rate-limit key (IP, user ID, API key) maps to a Durable Object
instance; the instance stores a ring of timestamped hit buckets and enforces the limit
atomically. Cloudflare's built-in Rate Limiting product handles simple cases, but Durable
Objects unlock custom token costs, per-user burst allowances, and dynamic limit adjustments.

## Threat Model

**Attacker goal**: exceed an API rate limit by exploiting window boundary resets, racing
concurrent requests across edge nodes, or inflating the Durable Object's storage state.

Attack scenarios:

- **Boundary burst**: a fixed-window counter resets at T=60; an attacker sends 100 requests
  at T=59 and 100 more at T=61, achieving 200 req/min against a 100 req/min limit.
- **Distributed hammering**: an attacker routes requests through multiple Cloudflare colos
  simultaneously; without a centralised counter, per-colo counters each allow the full limit.
- **Counter inflation via key enumeration**: an attacker creates millions of unique rate-limit
  keys (rotating IPs), each allowed the limit; without a global concurrency guard this causes
  unbounded Durable Object storage growth.
- **Cost-asymmetry bypass**: a cheap read endpoint is rate-limited equally to an expensive
  write endpoint; the attacker saturates cheap reads while the expensive operations are
  unaffected.

## Implementation — Sliding-Window Durable Object

```typescript
// rate-limiter/src/sliding-window.ts
import { DurableObject } from 'cloudflare:workers';

interface Bucket {
  windowStart: number; // unix seconds, truncated to bucket size
  count: number;
}

interface RateLimitConfig {
  windowSec: number;     // total window length in seconds (e.g. 60)
  bucketSec: number;     // sub-bucket granularity (e.g. 1 — per-second buckets)
  limit: number;         // max requests in the full window
  cost?: number;         // request weight (default 1)
}

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;       // unix timestamp when the oldest bucket expires
  retryAfter?: number;   // seconds until at least one slot opens
}

export class SlidingWindowRateLimiter extends DurableObject {
  private buckets: Map<number, number> = new Map(); // windowStart -> count
  private loaded = false;

  async check(config: RateLimitConfig): Promise<RateLimitResult> {
    await this.loadBuckets();
    const cost = config.cost ?? 1;
    const nowSec = Math.floor(Date.now() / 1000);
    const windowStart = nowSec - config.windowSec;

    // Evict expired buckets
    for (const [ts] of this.buckets) {
      if (ts <= windowStart) this.buckets.delete(ts);
    }

    // Count requests within the sliding window
    let total = 0;
    for (const [, count] of this.buckets) total += count;

    if (total + cost > config.limit) {
      // Find the earliest bucket timestamp so we can advise when space opens
      let earliest = Infinity;
      for (const [ts] of this.buckets) if (ts < earliest) earliest = ts;

      const retryAfter = earliest === Infinity
        ? config.bucketSec
        : earliest + config.windowSec - nowSec + 1;

      return {
        allowed: false,
        remaining: Math.max(0, config.limit - total),
        resetAt: nowSec + retryAfter,
        retryAfter: Math.max(1, retryAfter),
      };
    }

    // Increment current bucket
    const currentBucket = Math.floor(nowSec / config.bucketSec) * config.bucketSec;
    this.buckets.set(currentBucket, (this.buckets.get(currentBucket) ?? 0) + cost);

    // Persist atomically using Durable Object storage
    await this.ctx.storage.put(`bucket:${currentBucket}`, this.buckets.get(currentBucket));

    // Schedule alarm to clean up expired buckets
    const alarmTime = (currentBucket + config.windowSec + config.bucketSec) * 1000;
    const existing = await this.ctx.storage.getAlarm();
    if (!existing || existing > alarmTime) {
      await this.ctx.storage.setAlarm(alarmTime);
    }

    return {
      allowed: true,
      remaining: config.limit - total - cost,
      resetAt: currentBucket + config.windowSec,
    };
  }

  async alarm(): Promise<void> {
    // Evict all expired buckets from storage on alarm
    const nowSec = Math.floor(Date.now() / 1000);
    const all = await this.ctx.storage.list<number>({ prefix: 'bucket:' });
    const toDelete: string[] = [];
    for (const [key, _] of all) {
      const ts = parseInt(key.slice(7), 10);
      if (!isNaN(ts) && ts < nowSec - 120) toDelete.push(key); // 2-min grace
    }
    if (toDelete.length > 0) await this.ctx.storage.delete(toDelete);
  }

  private async loadBuckets(): Promise<void> {
    if (this.loaded) return;
    const all = await this.ctx.storage.list<number>({ prefix: 'bucket:' });
    this.buckets = new Map();
    for (const [key, count] of all) {
      const ts = parseInt(key.slice(7), 10);
      if (!isNaN(ts)) this.buckets.set(ts, count);
    }
    this.loaded = true;
  }

  // HTTP interface so the Worker can call the DO via fetch
  async fetch(request: Request): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    const config = await request.json<RateLimitConfig>();
    const result = await this.check(config);
    return Response.json(result);
  }
}
```

## Hardening — Worker Gateway with Rate-Limit Headers

```typescript
// rate-limiter/src/index.ts
export interface Env {
  RATE_LIMITER: DurableObjectNamespace;
}

// Derive a rate-limit key from the request — prefer authenticated user ID over IP
function rateLimitKey(request: Request): string {
  // Prefer the verified user ID set by upstream auth middleware
  const userId = request.headers.get('X-Verified-User-Id');
  if (userId) return `user:${userId}`;

  // Fall back to IP — use CF-Connecting-IP (set by Cloudflare, not spoofable)
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  return `ip:${ip}`;
}

// Map endpoint paths to rate-limit configs with different costs and limits
function getRateLimitConfig(url: URL): RateLimitConfig {
  if (url.pathname.startsWith('/api/expensive')) {
    return { windowSec: 60, bucketSec: 5, limit: 10, cost: 5 };
  }
  if (url.pathname.startsWith('/api/search')) {
    return { windowSec: 60, bucketSec: 1, limit: 30, cost: 2 };
  }
  // Default: 100 req/min with 1-second bucket granularity
  return { windowSec: 60, bucketSec: 1, limit: 100, cost: 1 };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = rateLimitKey(request);
    const config = getRateLimitConfig(url);

    // Route to a stable Durable Object instance for this key
    const id = env.RATE_LIMITER.idFromName(key);
    const stub = env.RATE_LIMITER.get(id);

    let result: RateLimitResult;
    try {
      const resp = await stub.fetch('https://internal/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      result = await resp.json<RateLimitResult>();
    } catch {
      // Fail open on Durable Object error — prefer availability over strict rate limiting,
      // but log the failure for alerting
      console.error('Rate limiter DO unavailable — failing open');
      return fetch(request);
    }

    // Attach standard rate-limit headers to all responses
    const rlHeaders = {
      'RateLimit-Limit': String(config.limit),
      'RateLimit-Remaining': String(result.remaining),
      'RateLimit-Reset': String(result.resetAt),
      'RateLimit-Policy': `${config.limit};w=${config.windowSec}`,
    };

    if (!result.allowed) {
      return new Response(
        JSON.stringify({ error: 'rate_limit_exceeded', retryAfter: result.retryAfter }),
        {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': String(result.retryAfter ?? config.bucketSec),
            ...rlHeaders,
          },
        }
      );
    }

    // Forward to the origin and attach rate-limit headers to the response
    const origin = await fetch(request);
    const response = new Response(origin.body, origin);
    for (const [k, v] of Object.entries(rlHeaders)) response.headers.set(k, v);
    return response;
  },
};

// Re-export the Durable Object class so wrangler picks it up
export { SlidingWindowRateLimiter };
```

## Anti-patterns

- **In-memory counters in the Worker**: each isolate instance has its own counter; distributed
  traffic across colos bypasses the limit entirely.
- **Fixed-window counters at window boundaries**: a client that knows the reset time can double
  its effective rate by bursting just before and just after the boundary.
- **Using IP as the only rate-limit key**: IPv6 ranges give attackers a large pool of addresses;
  always prefer authenticated user ID when available; combine both for defence in depth.
- **Never evicting old buckets**: unbounded bucket accumulation in Durable Object storage causes
  reads to slow down and storage costs to grow; always set an alarm to purge expired entries.
- **Silently discarding the Retry-After header**: clients that do not back off with exponential
  jitter will retry immediately, amplifying load during an outage.

## Gotchas

- **Durable Object location latency**: a DO instance is pinned to a single colo; requests from
  distant colos incur network RTT on every rate-limit check. Use `locationHint` in `idFromName`
  to colocate the DO near your primary origin.
- **Concurrency within a single DO**: Durable Objects process requests sequentially with a
  concurrency model similar to `async_hooks`; high-throughput keys (e.g. a viral user) become
  a bottleneck — shard by time bucket or use Cloudflare's native rate limiting for hot keys.
- **Clock drift across colos**: `Date.now()` in Workers is accurate to milliseconds; however,
  the DO and the calling Worker may disagree by up to a few hundred milliseconds — use the DO's
  own `Date.now()` for all bucket calculations to avoid off-by-one bucket errors.
- **Fail-open vs. fail-closed decision**: failing open preserves availability but allows limit
  bypass during outages; failing closed protects downstream services but causes 429s during
  storage unavailability. Document the chosen behaviour and alert on DO errors.
- **`idFromName` is deterministic**: the same key always maps to the same DO instance across
  Cloudflare's global network; key predictability means an attacker who discovers the naming
  scheme cannot influence DO routing, but also cannot be redirected to a different instance.

## Verification

```bash
# 1. Burst 11 requests against a limit of 10/min — 11th must return 429
for i in $(seq 1 11); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-Verified-User-Id: test-user-boundary" \
    https://api.example.workers.dev/api/default)
  echo "Request $i: $STATUS"
done
# expect: first 10 → 200, 11th → 429

# 2. Boundary burst test — send 5 requests just before second 60, then 5 after reset
# With sliding window, total 10 in flight during the window = still blocked at 11

# 3. Verify Retry-After header is present on 429
curl -sI -H "X-Verified-User-Id: test-user-429" \
  https://api.example.workers.dev/api/default | grep -i retry-after

# 4. After retryAfter seconds, a new request must succeed
sleep $(curl -sI ... | grep -i retry-after | awk '{print $2}')
curl -s -o /dev/null -w "%{http_code}" ...
# expect: 200
```

## Related

- `token-bucket-rate-limiting-durable-objects.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `cloudflare-rate-limiting-v2-api-abuse-prevention.md`
- `ato-behavioral-anomaly-scoring-d1.md`
- `durable-objects-auth-patterns.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers — RateLimit headers
- https://blog.cloudflare.com/rate-limiting-with-durable-objects/
