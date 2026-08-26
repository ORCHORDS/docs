# Token Bucket Rate Limiter Using Durable Objects

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your API is hit with bursts of requests from individual users or API keys, causing downstream services to be overwhelmed or unfairly starved. You need per-user or per-key rate limiting that allows short bursts while enforcing a long-term average throughput ceiling, and you need these limits to be enforced consistently across all Worker instances worldwide.

## Context

Cloudflare Workers run on hundreds of PoPs globally. A simple in-memory counter per Worker process is useless for rate limiting because each isolate has its own memory. KV could store counts but suffers from eventual consistency — multiple Workers could all read the same stale counter and allow more requests than intended. Durable Objects solve this by providing a single-threaded, strongly-consistent compute unit that colocates with storage. One DO per user/key acts as the authoritative token bucket for that entity, serialising all rate-limit decisions.

## Solution

Create one Durable Object per rate-limited entity (user ID, API key, IP). The DO maintains a token count and a last-refill timestamp in its storage. On each request the gateway Worker routes to the DO to consume a token. The DO refills tokens based on elapsed time using a scheduled alarm for idle cleanup and hibernation.

```typescript
// wrangler.toml excerpt
// [[durable_objects.bindings]]
// name = "RATE_LIMITER"
// class_name = "TokenBucketDO"

export interface Env {
  RATE_LIMITER: DurableObjectNamespace;
}

// --- Durable Object ---

interface BucketState {
  tokens: number;
  lastRefillMs: number;
}

const BUCKET_CONFIG = {
  tier1: { capacity: 60,  refillPerSecond: 1   },  // 60 req/min burst
  tier2: { capacity: 300, refillPerSecond: 5   },  // 300 req/min burst
  tier3: { capacity: 600, refillPerSecond: 10  },  // 10 req/s sustained
} as const;

type Tier = keyof typeof BUCKET_CONFIG;

export class TokenBucketDO implements DurableObject {
  private state: DurableObjectState;
  private bucket: BucketState | null = null;
  private tier: Tier = 'tier1';

  constructor(state: DurableObjectState, _env: Env) {
    this.state = state;
  }

  private async loadBucket(): Promise<BucketState> {
    if (this.bucket) return this.bucket;
    const stored = await this.state.storage.get<BucketState>('bucket');
    const cfg = BUCKET_CONFIG[this.tier];
    this.bucket = stored ?? { tokens: cfg.capacity, lastRefillMs: Date.now() };
    return this.bucket;
  }

  private refill(bucket: BucketState): BucketState {
    const cfg = BUCKET_CONFIG[this.tier];
    const nowMs = Date.now();
    const elapsedSec = Math.max(0, (nowMs - bucket.lastRefillMs) / 1000);
    const newTokens = Math.min(
      cfg.capacity,
      bucket.tokens + elapsedSec * cfg.refillPerSecond
    );
    return { tokens: newTokens, lastRefillMs: nowMs };
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Allow callers to override tier per request (set by gateway from JWT claim)
    const requestedTier = request.headers.get('X-Rate-Tier') as Tier | null;
    if (requestedTier && requestedTier in BUCKET_CONFIG) {
      this.tier = requestedTier;
    }

    if (url.pathname === '/check') {
      // Non-consuming peek — useful for monitoring dashboards
      const bucket = await this.loadBucket();
      const refilled = this.refill(bucket);
      const cfg = BUCKET_CONFIG[this.tier];
      return Response.json({
        tokens: refilled.tokens,
        capacity: cfg.capacity,
        refillPerSecond: cfg.refillPerSecond,
      });
    }

    if (url.pathname === '/consume') {
      const cost = Number(url.searchParams.get('cost') ?? '1');
      const bucket = await this.loadBucket();
      const refilled = this.refill(bucket);
      const cfg = BUCKET_CONFIG[this.tier];

      const allowed = refilled.tokens >= cost;
      if (allowed) {
        refilled.tokens -= cost;
      }

      // Persist updated state
      this.bucket = refilled;
      await this.state.storage.put('bucket', refilled);

      // Schedule cleanup alarm if idle — DO hibernates when no requests arrive
      await this.state.storage.setAlarm(Date.now() + 60_000); // wake in 60 s

      const remaining = Math.floor(refilled.tokens);
      const resetSec = Math.ceil((cfg.capacity - refilled.tokens) / cfg.refillPerSecond);

      return Response.json(
        { allowed, remaining, resetSec, tier: this.tier },
        {
          status: allowed ? 200 : 429,
          headers: {
            'X-RateLimit-Limit':     String(cfg.capacity),
            'X-RateLimit-Remaining': String(remaining),
            'X-RateLimit-Reset':     String(Math.ceil(Date.now() / 1000) + resetSec),
            'Retry-After':           allowed ? '0' : String(resetSec),
          },
        }
      );
    }

    return new Response('Not found', { status: 404 });
  }

  // Alarm fires after idle period — evict DO from memory to reduce billing
  async alarm(): Promise<void> {
    const bucket = await this.loadBucket();
    const refilled = this.refill(bucket);
    const cfg = BUCKET_CONFIG[this.tier];
    // If tokens are at capacity, nothing needs to be kept; storage stays for
    // history but the DO will hibernate after returning.
    if (refilled.tokens >= cfg.capacity) {
      // Tokens fully refilled — no active user, safe to clear and hibernate
      await this.state.storage.deleteAll();
      this.bucket = null;
    } else {
      // Partial state — persist and re-arm alarm
      this.bucket = refilled;
      await this.state.storage.put('bucket', refilled);
      await this.state.storage.setAlarm(Date.now() + 60_000);
    }
  }
}

// --- Gateway Worker ---

async function getRateLimitKey(request: Request): Promise<string> {
  // Prefer authenticated user ID from JWT; fall back to hashed IP
  const userId = request.headers.get('X-User-Id');
  if (userId) return `user:${userId}`;
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  return `ip:${ip}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const key = await getRateLimitKey(request);
    const tier = request.headers.get('X-User-Tier') ?? 'tier1';

    // Route to the correct DO shard
    const id = env.RATE_LIMITER.idFromName(key);
    const stub = env.RATE_LIMITER.get(id);

    const rlRequest = new Request('https://do/consume?cost=1', {
      headers: { 'X-Rate-Tier': tier },
    });
    const rlResponse = await stub.fetch(rlRequest);
    const { allowed, remaining, resetSec } = await rlResponse.json<any>();

    if (!allowed) {
      return new Response(JSON.stringify({ error: 'Rate limit exceeded' }), {
        status: 429,
        headers: {
          'Content-Type':          'application/json',
          'X-RateLimit-Remaining': '0',
          'Retry-After':           String(resetSec),
        },
      });
    }

    // Forward to actual service, injecting rate-limit headers
    const response = await fetch(request);
    const mutable = new Response(response.body, response);
    mutable.headers.set('X-RateLimit-Remaining', String(remaining));
    return mutable;
  },
};
```

## Implementation Details

**Token refill math.** Tokens accumulate continuously based on wall-clock elapsed time. The formula `tokens = min(capacity, tokens + elapsed * rate)` is evaluated lazily on every consume call — no background timer is needed in the DO for normal operation.

**Multi-tier limits.** The tier is carried in an `X-Rate-Tier` header set by the gateway after validating the JWT. The DO reads the header each call, so tier upgrades take effect immediately on the next request without DO restart.

**Burst allowance.** `capacity` defines burst size. A tier-3 user with capacity 600 and rate 10/s can absorb a 600-request burst before being throttled, then sustain 10 req/s indefinitely.

**Rate-limit header injection.** RFC 6585 / draft-ietf-httpapi-ratelimit-headers compliant headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`) are set on every response — both 200 and 429 — so clients can implement back-off without guessing.

**DO hibernation.** The alarm fires 60 s after the last request. If tokens are full the DO clears its storage and hibernates, eliminating idle billing. On the next request a fresh bucket is initialised at full capacity.

**DO locality.** `idFromName(key)` consistently routes the same key to the same DO shard regardless of which PoP serves the Worker. Cloudflare locates the DO near the region where it was first created.

## Anti-patterns

- **Using KV for counters.** KV is eventually consistent; two Workers can both read a stale value and both grant requests that should have been denied.
- **Fixed-window counters.** They create a thundering-herd at the window boundary (e.g., all clients retry at second :00). Token buckets smooth traffic naturally.
- **One DO for all users.** A single DO serialises every rate-limit check globally, becoming a bottleneck. Always use one DO per independent rate-limit entity.
- **Not setting the alarm.** Without an alarm, an idle DO continues to count against your DO active time billing indefinitely.

## Gotchas

- DO `idFromName` hashes are deterministic but not reversible. Store a readable key in DO storage if you need to query it from outside.
- Alarms fire at least once but are not guaranteed exactly on time. Add a 5–10 % grace margin to token calculations to avoid penalising users for minor clock drift.
- `state.storage.put` is synchronous in the sense that it flushes before the `fetch` handler returns — data is durable by the time the response is sent.
- If the DO is evicted mid-request (very rare), the next call reloads from storage. Always persist state before returning.
- Workers KV can be used for a coarse, non-authoritative rate limit check before hitting the DO to avoid DO costs for obviously clean traffic.

## Verification

```bash
# Consume 10 tokens rapidly and observe 429
for i in $(seq 1 70); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-User-Id: test-user" \
    -H "X-User-Tier: tier1" \
    https://api.example.com/endpoint)
  echo "Request $i: $STATUS"
done
# Expect first 60 to return 200, remainder to return 429

# Check bucket state
curl -H "X-User-Id: test-user" https://do-debug.example.com/check
```

## Related

- `circuit-breaker-durable-objects` — using DOs for stateful circuit state
- `workers-bulkhead-pattern-queue-isolation` — isolating capacity per service
- `workers-api-gateway-pattern` — gateway layer that invokes rate limiter

## Sources

- Cloudflare Durable Objects docs: https://developers.cloudflare.com/durable-objects/
- Cloudflare DO Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Token bucket algorithm: https://en.wikipedia.org/wiki/Token_bucket
- IETF RateLimit Headers draft: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
