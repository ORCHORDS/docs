# Sliding Window Counter Pattern — Durable Objects

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A fixed-window rate limiter allows a burst of 2× the quota at window boundaries: a client sends 100 requests in the last second of window A and 100 requests in the first second of window B — both within quota, but 200 requests arrive in a 2-second span. A sliding window counter solves this by prorating the previous window's count based on how far the current time has progressed into the new window. Durable Objects provide the single-threaded, strongly consistent storage needed to implement it without race conditions.

## Context

- A Durable Object is chosen over KV because KV is eventually consistent and does not support atomic compare-and-swap, making concurrent counter updates unsafe.
- Each rate-limited key (IP, API key, tenant) maps to one Durable Object instance — the key becomes the DO name.
- The sliding window algorithm stores two values: the count in the previous complete window and the count in the current partial window. At request time, the effective count is `prevCount × (1 − elapsed/windowMs) + currCount`.
- The DO alarm API is used to reset counters, avoiding stale state accumulation from inactive keys.
- This pattern covers HTTP 429 enforcement; for token-bucket semantics see `token-bucket-durable-objects.md`.

---

## Durable Object Implementation

```typescript
// src/do/sliding-window-limiter.ts
export interface SlidingWindowState {
  windowStart: number;   // epoch ms of current window start
  currCount: number;     // requests in the current window
  prevCount: number;     // requests in the previous window
}

export class SlidingWindowLimiter implements DurableObject {
  private state: DurableObjectState;
  private windowMs: number;
  private limit: number;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    // Read config from env so the same DO class serves multiple limits
    this.windowMs = Number(env.RATE_LIMIT_WINDOW_MS ?? 60_000); // default 1 min
    this.limit = Number(env.RATE_LIMIT_MAX ?? 100);
  }

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();

    // Load persisted state (defaults for first request)
    let windowStart: number = (await this.state.storage.get<number>('windowStart')) ?? now;
    let currCount: number  = (await this.state.storage.get<number>('currCount'))  ?? 0;
    let prevCount: number  = (await this.state.storage.get<number>('prevCount'))  ?? 0;

    // Check whether we have crossed into a new window
    const elapsed = now - windowStart;

    if (elapsed >= 2 * this.windowMs) {
      // Two full windows have passed — reset entirely
      prevCount = 0;
      currCount = 0;
      windowStart = now;
    } else if (elapsed >= this.windowMs) {
      // Exactly one window boundary crossed
      prevCount = currCount;
      currCount = 0;
      windowStart = windowStart + this.windowMs;
    }

    // Sliding window effective count:
    // weight previous window by how much of the current window remains unused
    const windowElapsed = now - windowStart;
    const prevWeight = Math.max(0, 1 - windowElapsed / this.windowMs);
    const effectiveCount = Math.floor(prevCount * prevWeight) + currCount;

    if (effectiveCount >= this.limit) {
      const retryAfterMs = this.windowMs - windowElapsed;
      return new Response(
        JSON.stringify({ error: 'rate_limit_exceeded', retryAfterMs }),
        {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': String(Math.ceil(retryAfterMs / 1000)),
            'X-RateLimit-Limit': String(this.limit),
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': String(Math.ceil((windowStart + this.windowMs) / 1000)),
          },
        }
      );
    }

    // Increment and persist atomically within the single-threaded DO
    currCount += 1;
    await this.state.storage.put({
      windowStart,
      currCount,
      prevCount,
    });

    // Schedule alarm to clean up state after two idle windows
    const alarmTime = windowStart + 2 * this.windowMs + 1000;
    const existingAlarm = await this.state.storage.getAlarm();
    if (!existingAlarm || existingAlarm > alarmTime) {
      await this.state.storage.setAlarm(alarmTime);
    }

    const remaining = this.limit - effectiveCount - 1;
    return new Response(JSON.stringify({ allowed: true, remaining }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'X-RateLimit-Limit': String(this.limit),
        'X-RateLimit-Remaining': String(remaining),
        'X-RateLimit-Reset': String(Math.ceil((windowStart + this.windowMs) / 1000)),
      },
    });
  }

  async alarm(): Promise<void> {
    // Clear state for inactive keys to avoid storage accumulation
    await this.state.storage.deleteAll();
  }
}
```

---

## Worker Entrypoint — Route to DO by Key

```typescript
// src/index.ts
export { SlidingWindowLimiter } from './do/sliding-window-limiter';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const rateLimitKey = getRateLimitKey(request);
    const id = env.SLIDING_WINDOW_LIMITER.idFromName(rateLimitKey);
    const stub = env.SLIDING_WINDOW_LIMITER.get(id);

    // Check rate limit before proxying to the actual handler
    const limitResponse = await stub.fetch(new Request('https://limiter/', { method: 'POST' }));

    if (limitResponse.status === 429) {
      return limitResponse; // Forward 429 with Retry-After headers
    }

    // Copy rate limit headers to the real response
    const realResponse = await handleRequest(request, env);
    const headers = new Headers(realResponse.headers);
    limitResponse.headers.forEach((v, k) => {
      if (k.startsWith('x-ratelimit-')) headers.set(k, v);
    });

    return new Response(realResponse.body, {
      status: realResponse.status,
      headers,
    });
  },
};

function getRateLimitKey(request: Request): string {
  // Prefer API key; fall back to IP
  const apiKey = <redacted-secret>'X-API-Key');
  if (apiKey) return `apikey:${apiKey}`;
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  return `ip:${ip}`;
}
```

---

## Wrangler Configuration

```toml
# wrangler.toml
name = "api-gateway"
main = "src/index.ts"

[[durable_objects.bindings]]
name = "SLIDING_WINDOW_LIMITER"
class_name = "SlidingWindowLimiter"

[vars]
RATE_LIMIT_WINDOW_MS = "60000"
RATE_LIMIT_MAX = "100"

[[migrations]]
tag = "v1"
new_classes = ["SlidingWindowLimiter"]
```

---

## Per-Route Limit Tiers

```typescript
// src/lib/rate-limit-config.ts
export interface RateLimitTier {
  windowMs: number;
  max: number;
}

export const TIER_MAP: Record<string, RateLimitTier> = {
  '/api/search':      { windowMs: 60_000, max: 30 },
  '/api/export':      { windowMs: 60_000, max: 5  },
  '/api/ingest':      { windowMs: 10_000, max: 50 },
  '/api/':            { windowMs: 60_000, max: 100 }, // default
};

export function tierFor(pathname: string): RateLimitTier {
  for (const [prefix, tier] of Object.entries(TIER_MAP)) {
    if (pathname.startsWith(prefix)) return tier;
  }
  return TIER_MAP['/api/'];
}
```

---

## Anti-patterns

- **Using KV for the counter**: KV does not provide atomic increment under concurrent writes; two simultaneous requests can both read `count = 99`, both increment to `100`, and both succeed when the limit should have been hit.
- **Using a fixed-window counter**: allows 2× burst at window boundaries. Always prefer sliding window for user-facing APIs.
- **One DO per route instead of per key**: a single DO instance becomes a concurrency bottleneck since each `fetch()` is serialized. Shard by key.
- **Not setting a DO alarm**: inactive DO instances accumulate storage and are billed indefinitely. Always schedule a cleanup alarm.
- **Resetting `currCount` on every window without carrying `prevCount`**: produces a fixed window, not a sliding one.

## Gotchas

- DO `fetch()` calls are serialized within a single instance; concurrent requests from the same key queue up. Typical latency is < 5 ms per call from the same Cloudflare region.
- `state.storage.put({ ... })` with an object upserts multiple keys atomically, but `state.storage.get` with a single key returns one value. Batch your reads: `await this.state.storage.get(['windowStart', 'currCount', 'prevCount'])` returns a `Map`.
- The effective count formula uses integer flooring (`Math.floor`) to avoid allowing a fractional extra request.
- DO instances are evicted from memory after ~10 seconds of inactivity; the next request warms them from storage in ~1–2 ms. Design for this cold-start latency.

## Verification

```bash
# Send 110 requests to an endpoint limited at 100/min; expect 429s starting at request 101
for i in $(seq 1 110); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-API-Key: test-key" \
    https://api.example.com/api/ping)
  echo "$i: $STATUS"
done | grep 429 | head -5
# Should see 429 starting at line 101

# Confirm sliding behaviour: wait 30s (half window) then send 50 requests
sleep 30
for i in $(seq 1 50); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-API-Key: test-key" \
    https://api.example.com/api/ping
done
# All 50 should be 200 (prev 100 × 0.5 weight = 50 effective; 50 new = 100 total, at limit)
```

## Related

- `token-bucket-durable-objects.md`
- `kv-rate-limiting.md`
- `distributed-lock-durable-objects.md`
- `semaphore-concurrency-durable-objects.md`
- `api-rate-limiting-detail.md`

## Sources

- Cloudflare Durable Objects docs — Storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Cloudflare Durable Objects docs — Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- "A better rate limiting algorithm" — Cloudflare blog (sliding window): https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
