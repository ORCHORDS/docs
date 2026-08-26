# Token Bucket Rate Limiting with Durable Objects

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project needs per-user API rate limits that survive across the full fleet of Workers handling a user's requests — not a single-instance approximation. A Workers-local counter resets on every new isolate, lets bursts slip through during cold-starts, and cannot enforce limits across geographic PoPs. Coordinated, exact rate limiting requires shared mutable state: a Durable Object holding the token bucket for each user.

## Context

The **token bucket** algorithm grants a fixed number of tokens per refill period. Each request consumes one token; excess requests are rejected (or deferred). Compared to fixed-window counters, token buckets allow controlled short bursts while bounding sustained throughput — a better UX fit for social API clients that may burst briefly when scrolling feeds. Durable Objects provide the single-writer, strongly-consistent state needed to implement the algorithm correctly across the Workers fleet. This pattern differs from the general `rate-limiting-architecture.md` article: it focuses specifically on the Durable Object internal state machine and the concurrency model that makes it safe.

## 1. Token Bucket Durable Object

The DO stores `tokens` and `lastRefill` in its in-memory state (not storage) between requests to the same instance, minimising latency. Storage is written only when tokens actually change, reducing D1/DO storage costs.

```typescript
export class TokenBucketDO implements DurableObject {
  private tokens: number;
  private lastRefill: number;
  private readonly capacity: number;
  private readonly refillRate: number; // tokens per second

  constructor(state: DurableObjectState, env: Env) {
    this.capacity = 60;
    this.refillRate = 1; // 1 token/sec → 60/min sustained, burst up to 60
    this.tokens = this.capacity;
    this.lastRefill = Date.now();
  }

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(
      this.capacity,
      this.tokens + elapsed * this.refillRate,
    );
    this.lastRefill = now;

    if (this.tokens < 1) {
      const retryAfter = Math.ceil((1 - this.tokens) / this.refillRate);
      return new Response('Too Many Requests', {
        status: 429,
        headers: {
          'Retry-After': String(retryAfter),
          'X-RateLimit-Limit': String(this.capacity),
          'X-RateLimit-Remaining': '0',
        },
      });
    }

    this.tokens -= 1;
    return new Response('ok', {
      status: 200,
      headers: {
        'X-RateLimit-Limit': String(this.capacity),
        'X-RateLimit-Remaining': String(Math.floor(this.tokens)),
      },
    });
  }
}
```

## 2. Routing Requests to the Correct DO Instance

Name each DO stub on the user ID so every Worker request for the same user reaches the same Durable Object instance — the key invariant that makes the counter exact.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const userId = getUserId(request); // extracted from JWT or session cookie
    if (!userId) return new Response('Unauthorized', { status: 401 });

    const doId = env.TOKEN_BUCKET.idFromName(`rate:${userId}`);
    const stub = env.TOKEN_BUCKET.get(doId);

    const limitResponse = await stub.fetch(
      new Request('https://do.internal/check'),
    );

    if (limitResponse.status === 429) {
      return new Response('Rate limit exceeded', {
        status: 429,
        headers: Object.fromEntries(limitResponse.headers),
      });
    }

    // Forward to the real handler
    return handleApiRequest(request, env);
  },
};
```

`wrangler.toml`:

```toml
[[durable_objects.bindings]]
name = "TOKEN_BUCKET"
class_name = "TokenBucketDO"

[[migrations]]
tag = "v1"
new_classes = ["TokenBucketDO"]
```

## 3. Tiered Capacity by Plan

Inject capacity and refill rate via a request header set by the calling Worker, resolved from KV at the edge before the DO call, so the DO itself stays generic.

```typescript
// In the Worker before calling the DO stub
const plan = await env.KV.get(`plan:${userId}`) ?? 'free';
const limits: Record<string, { capacity: number; rate: number }> = {
  free:    { capacity: 60,   rate: 1   },
  pro:     { capacity: 600,  rate: 10  },
  creator: { capacity: 3000, rate: 50  },
};
const { capacity, rate } = limits[plan];

const doRequest = new Request('https://do.internal/check', {
  headers: {
    'X-Capacity': String(capacity),
    'X-Refill-Rate': String(rate),
  },
});
const limitResponse = await stub.fetch(doRequest);
```

Inside the DO `fetch`, read those headers and override the instance fields before computing the refill. Store plan tier in the DO in-memory state after first resolution to avoid re-reading on every sub-request.

## 4. Graceful Degradation on DO Unavailability

Durable Objects can be temporarily unavailable during a datacenter incident. Wrap the stub call in a timeout and fall back to a generous local Worker limit rather than hard-failing all API traffic.

```typescript
async function checkRateLimit(
  stub: DurableObjectStub,
  fallbackLimit: number,
): Promise<{ allowed: boolean; headers: Record<string, string> }> {
  const timeout = new Promise<Response>((_, reject) =>
    setTimeout(() => reject(new Error('timeout')), 150),
  );
  try {
    const res = await Promise.race([stub.fetch('https://do.internal/check'), timeout]);
    return {
      allowed: res.status !== 429,
      headers: Object.fromEntries(res.headers),
    };
  } catch {
    // DO unreachable — apply local Worker-level counter as fallback
    return { allowed: localAllowed(fallbackLimit), headers: {} };
  }
}
```

## Anti-patterns

- **Using `idFromString(userId)` with untrusted input** — `idFromString` accepts arbitrary hex; `idFromName` is safer for application-controlled identifiers and is the standard pattern.
- **Persisting tokens to DO storage on every request** — storage writes add latency and cost; keep tokens in memory and write only on significant state changes or during hibernation.
- **Sharing one DO instance across all users** — a single `idFromName('global')` becomes a hot spot and a single point of failure; always shard by user or tenant ID.
- **Returning 503 when the DO is unreachable** — prefer a degraded but functional response; a rate-limit enforcement outage should not take down the product.

## Gotchas

- DO in-memory state is lost on instance eviction (typically after ~30 s of inactivity for free/standard plans). On next request `tokens` resets to `capacity`, which is intentional — an idle user gets a fresh bucket. Persist to storage only if exact carry-over across evictions is a product requirement.
- `Date.now()` in a DO runs at the PoP executing the DO, not the calling Worker's PoP. Both are wall-clock time and are reliable enough for token refill math; use it freely.
- A burst of concurrent Workers requests for the same user will queue inside the DO's single-threaded event loop — they will not race, but they may experience up to a few milliseconds of added latency under load.
- DO-to-Worker response serialization adds ~1–2 ms per round-trip. Put the DO check on the critical path only for endpoints that need enforcement; background analytics paths can use async audit logs instead.

## Verification

1. Send 61 rapid requests from a single user; assert exactly 60 return `200` and 1 returns `429`.
2. After 1 second pause, send 1 request; assert it returns `200` (token refilled).
3. Kill the DO binding in a staging deployment and send a request; assert the fallback path allows the request and does not return `500`.
4. Assign two users to different plan tiers in KV; assert each experiences the correct per-plan burst capacity.

## Related

- `rate-limiting-architecture-workers.md`
- `rate-limiting-architecture.md`
- `distributed-lock-design.md`
- `circuit-breaker-kv-state-machine.md`
- `competing-consumers-durable-objects.md`

## Sources

- Token Bucket algorithm — Wikipedia: https://en.wikipedia.org/wiki/Token_bucket
- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- Cloudflare Workers KV — plan tier lookup: https://developers.cloudflare.com/kv/
