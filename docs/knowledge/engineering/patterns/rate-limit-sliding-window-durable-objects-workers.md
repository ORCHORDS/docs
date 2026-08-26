# Sliding Window Rate Limiting with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need per-IP, per-user, or per-endpoint rate limiting that is accurate across all edge PoPs — not the approximate, PoP-local counting that KV or Workers' built-in rate limiting provide. A sliding window algorithm avoids the burst-at-boundary problem of fixed windows while remaining cheap to compute.

## Context

Cloudflare's native Rate Limiting product handles simple cases. For custom logic — burst capacity, composite keys, per-tier limits, dynamic limits stored in D1 — a `RateLimiterDO` gives you a strongly consistent counter with `blockConcurrencyWhile` atomicity, all within a single Durable Object instance per rate-limit key.

**Trade-off**: every request that needs rate limiting incurs one DO fetch (~1–5 ms in the same region). This is acceptable for authenticated API traffic; avoid it for anonymous static asset requests.

## RateLimiterDO and Worker

```typescript
// rate-limiter-do/index.ts
interface RateLimitConfig {
  windowMs:  number;  // e.g. 60_000 for 60 s
  maxTokens: number;  // e.g. 100 requests per window
}

interface RateLimitResult {
  allowed:   boolean;
  remaining: number;
  resetAt:   number;  // Unix ms when the oldest request in the window expires
}

export class RateLimiterDO {
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState, private env: Env) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/check') return new Response('Not found', { status: 404 });

    const config: RateLimitConfig = {
      windowMs:  parseInt(url.searchParams.get('windowMs')  ?? '60000'),
      maxTokens: parseInt(url.searchParams.get('maxTokens') ?? '100'),
    };

    const result = await this.storage.transaction(async (txn) => {
      return this.checkLimit(txn, config);
    });

    return Response.json(result, {
      status: result.allowed ? 200 : 429,
      headers: {
        'X-RateLimit-Remaining': String(result.remaining),
        'X-RateLimit-Reset':     String(Math.ceil(result.resetAt / 1_000)),
      },
    });
  }

  private async checkLimit(
    txn: DurableObjectTransaction,
    config: RateLimitConfig,
  ): Promise<RateLimitResult> {
    const now        = Date.now();
    const windowStart = now - config.windowMs;

    // Load existing timestamps from storage
    const timestamps: number[] = (await txn.get<number[]>('timestamps')) ?? [];

    // Evict timestamps outside the current window (sliding)
    const active = timestamps.filter((t) => t > windowStart);

    const allowed = active.length < config.maxTokens;

    if (allowed) {
      // Record this request
      active.push(now);
      await txn.put('timestamps', active);
    }

    // resetAt = when the oldest active timestamp will leave the window
    const resetAt = active.length > 0 ? active[0] + config.windowMs : now + config.windowMs;

    return {
      allowed,
      remaining: Math.max(0, config.maxTokens - active.length),
      resetAt,
    };
  }
}

// gateway-worker/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const key    = rateLimitKey(request, env);  // see key strategies below
    const doId   = env.RATE_LIMITER.idFromName(key);
    const stub   = env.RATE_LIMITER.get(doId);

    const limitRes = await stub.fetch(
      `https://internal/check?windowMs=60000&maxTokens=100`
    );

    if (limitRes.status === 429) {
      const { resetAt } = await limitRes.json<RateLimitResult>();
      return new Response('Rate limit exceeded', {
        status: 429,
        headers: {
          'Retry-After':       String(Math.ceil((resetAt - Date.now()) / 1_000)),
          'X-RateLimit-Reset': String(Math.ceil(resetAt / 1_000)),
        },
      });
    }

    // Forward to origin / process request
    return handleRequest(request, env);
  },
};

function rateLimitKey(request: Request, env: Env): string {
  const url  = new URL(request.url);
  const ip   = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  const user = request.headers.get('X-User-Id') ?? '';

  // Key strategies — pick one:
  // Per-IP:       return `ip:${ip}`;
  // Per-user:     return `user:${user}`;
  // Per-endpoint: return `endpoint:${url.pathname}`;
  // Composite:    return `user:${user}:endpoint:${url.pathname}`;
  return user ? `user:${user}` : `ip:${ip}`;
}

async function handleRequest(request: Request, env: Env): Promise<Response> {
  // Replace with real upstream call
  return Response.json({ ok: true });
}
```

## Wrangler Configuration

```jsonc
{
  "name": "rate-limited-gateway",
  "durable_objects": {
    "bindings": [{ "name": "RATE_LIMITER", "class_name": "RateLimiterDO" }]
  },
  "migrations": [
    { "tag": "v1", "new_classes": ["RateLimiterDO"] }
  ]
}
```

## Key Namespace Strategies

| Strategy | Key format | DO instance per | Use when |
|---|---|---|---|
| Per-IP | `ip:{CF-Connecting-IP}` | IP address | Anonymous APIs, DDoS mitigation |
| Per-user | `user:{user_id}` | Authenticated user | Subscription tier enforcement |
| Per-endpoint | `endpoint:{pathname}` | API route | Protecting expensive endpoints |
| Composite | `user:{id}:ep:{path}` | User + route pair | Fine-grained per-resource limits |
| Global | `global` | Entire service | Emergency circuit breaker |

## Sliding Window vs Fixed Window

| Property | Fixed window | Sliding window (this pattern) |
|---|---|---|
| Burst at boundary | Yes — 2× limit possible at minute boundary | No — limit is enforced over any 60-second span |
| Memory per key | O(1) — just a counter | O(n) — one timestamp per request in window |
| Reset time accuracy | Approximate | Exact (`resetAt` = oldest timestamp + window) |

## Anti-patterns

- **One DO for all keys** — `idFromName(key)` ensures one DO per rate-limit key; using `idFromName('global')` for all traffic routes everything through one DO, creating a bottleneck.
- **Storing timestamps as a string** — store as `number[]`; JSON round-trips in `txn.put/get` handle serialisation automatically.
- **Skipping the transaction** — without `storage.transaction`, a concurrent `/check` call can read the same `timestamps` array, both see `active.length < maxTokens`, and both push a new timestamp, double-counting one token.
- **Not evicting old timestamps** — unbounded growth of the timestamps array eventually hits DO storage limits and slows `get`.

## Gotchas

- `storage.transaction` in DOs is a Durable Object–level mutex — it serialises concurrent calls to the same DO instance, which is correct here. It does **not** span multiple DO instances.
- `idFromName` is deterministic and globally unique — the same string always routes to the same DO instance across all PoPs.
- DO instances are co-located with the PoP closest to where they were first created. Subsequent requests are routed to that PoP — adds ~10–50 ms for geographically distant clients. For very latency-sensitive applications, consider a regional key suffix: `user:${id}:region:${request.cf?.region}`.
- The timestamps array can grow to `maxTokens` entries at most (eviction keeps it bounded); at 100 tokens × 8 bytes each = ~800 bytes — well within DO storage limits.

## Verification

```bash
# Fire 110 requests in quick succession (limit = 100)
for i in $(seq 1 110); do
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' \
    -H 'X-User-Id: test-user' \
    https://api.example.com/endpoint)
  echo "Request $i: $STATUS"
done

# Requests 101-110 should return 429
# After 60 seconds, fire another 10 — should all return 200
sleep 60
for i in $(seq 1 10); do
  curl -s -o /dev/null -w '%{http_code}\n' \
    -H 'X-User-Id: test-user' \
    https://api.example.com/endpoint
done
```

## Related

- `request-deduplication-workers-kv-fingerprint.md`
- `async-request-reply-workers-durable-objects.md`
- Cloudflare Durable Objects — Transactional Storage API
- Cloudflare Rate Limiting product (for simpler cases)

## Sources

- https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- https://developers.cloudflare.com/durable-objects/best-practices/
- https://developers.cloudflare.com/workers/platform/limits/
