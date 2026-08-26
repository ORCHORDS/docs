# Token Bucket Rate Limiting with Durable Objects

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

A sliding-window or fixed-window counter stored in KV rejects every request once the counter hits its ceiling, making burst traffic from legitimate users (mobile reconnects, batch uploads, retries on flaky connections) indistinguishable from abuse. You want to allow short bursts while enforcing a sustainable average rate, and you want that enforcement to be strongly consistent so two simultaneous requests from the same client cannot both "see" a non-empty bucket and both succeed when only one token remains.

Cloudflare KV is eventually consistent; a fixed-window counter in KV has a race window. Durable Objects offer a single-writer, strongly consistent storage primitive with colocated compute — exactly the right fit for a token bucket.

---

## Context

The **token bucket** algorithm models capacity as tokens:

- The bucket holds up to `capacity` tokens.
- Tokens refill at a constant rate (`refillRate` tokens per second).
- Each request consumes `cost` tokens (default 1).
- If fewer tokens than `cost` are available the request is rejected.

This naturally allows bursting up to `capacity` while enforcing an average rate of `refillRate` requests/second over time. Compared with leaky-bucket, token bucket is more caller-friendly because it absorbs legitimate short bursts.

**Why Durable Objects?**
Durable Objects guarantee that a single DO instance handles one request at a time (no parallel execution within an instance). This eliminates the race condition inherent in read-modify-write across distributed storage. The DO also runs at the Cloudflare PoP closest to the first request for that key, keeping latency low.

---

## Durable Object: TokenBucket

```typescript
// src/token-bucket.ts
export interface TokenBucketConfig {
  capacity: number;       // max tokens
  refillRate: number;     // tokens per second
  cost?: number;          // tokens per request (default 1)
}

export interface ConsumeResult {
  allowed: boolean;
  remaining: number;
  retryAfterMs: number;
}

export class TokenBucket implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState, _env: unknown) {
    this.state = state;
    // Block concurrency: only one fetch() executes at a time within this instance
    this.state.blockConcurrencyWhile(async () => {
      // Warm up storage; no-op if already initialised
    });
  }

  async fetch(request: Request): Promise<Response> {
    const config: TokenBucketConfig = await request.json();
    const { capacity, refillRate, cost = 1 } = config;

    const nowMs = Date.now();

    // Load persistent state
    const stored = await this.state.storage.get<{
      tokens: number;
      lastRefillMs: number;
    }>('bucket');

    let tokens = stored?.tokens ?? capacity;
    let lastRefillMs = stored?.lastRefillMs ?? nowMs;

    // Refill: add tokens proportional to elapsed time
    const elapsedSeconds = Math.max(0, (nowMs - lastRefillMs) / 1000);
    tokens = Math.min(capacity, tokens + elapsedSeconds * refillRate);
    lastRefillMs = nowMs;

    let allowed: boolean;
    let retryAfterMs = 0;

    if (tokens >= cost) {
      tokens -= cost;
      allowed = true;
    } else {
      allowed = false;
      const deficit = cost - tokens;
      retryAfterMs = Math.ceil((deficit / refillRate) * 1000);
    }

    // Persist updated state
    await this.state.storage.put('bucket', { tokens, lastRefillMs });

    const result: ConsumeResult = {
      allowed,
      remaining: Math.floor(tokens),
      retryAfterMs,
    };

    return Response.json(result, { status: allowed ? 200 : 429 });
  }
}
```

---

## Worker Integration

```typescript
// src/worker.ts
import { TokenBucket } from './token-bucket';

export { TokenBucket };

export interface Env {
  TOKEN_BUCKET: DurableObjectNamespace;
  RATE_LIMIT_CAPACITY: string;    // e.g. "100"
  RATE_LIMIT_REFILL_RATE: string; // e.g. "10"
}

// Derive a stable DO name per client identity
function bucketKey(request: Request, env: Env): string {
  // Use the validated user ID if authenticated, else IP
  const userId = request.headers.get('x-authenticated-user-id');
  if (userId) return `user:${userId}`;
  // CF-Connecting-IP is set by the Cloudflare edge; not spoofable from origin
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  return `ip:${ip}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const key = bucketKey(request, env);

    // Locate the DO instance for this client
    const id = env.TOKEN_BUCKET.idFromName(key);
    const stub = env.TOKEN_BUCKET.get(id);

    // Call the DO synchronously; it enforces serialisation internally
    const bucketResponse = await stub.fetch('https://internal/consume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        capacity: Number(env.RATE_LIMIT_CAPACITY),
        refillRate: Number(env.RATE_LIMIT_REFILL_RATE),
        cost: 1,
      }),
    });

    const result: { allowed: boolean; remaining: number; retryAfterMs: number } =
      await bucketResponse.json();

    if (!result.allowed) {
      return new Response('Too Many Requests', {
        status: 429,
        headers: {
          'Retry-After': String(Math.ceil(result.retryAfterMs / 1000)),
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Limit': env.RATE_LIMIT_CAPACITY,
        },
      });
    }

    // Propagate remaining tokens to the upstream handler
    request = new Request(request, {
      headers: {
        ...Object.fromEntries(request.headers),
        'X-RateLimit-Remaining': String(result.remaining),
        'X-RateLimit-Limit': env.RATE_LIMIT_CAPACITY,
      },
    });

    return handleApplication(request, env);
  },
};

async function handleApplication(request: Request, _env: Env): Promise<Response> {
  // Replace with real application logic
  return new Response('OK', { status: 200 });
}
```

---

## wrangler.toml Configuration

```toml
# wrangler.toml
name = "api-gateway"
main = "src/worker.ts"
compatibility_date = "2026-01-01"

[vars]
RATE_LIMIT_CAPACITY = "100"
RATE_LIMIT_REFILL_RATE = "10"

[[durable_objects.bindings]]
name = "TOKEN_BUCKET"
class_name = "TokenBucket"

[[migrations]]
tag = "v1"
new_classes = ["TokenBucket"]
```

---

## Tiered Rate Limits by Endpoint

Different endpoints often need different limits. Pass endpoint-specific config to the DO rather than using global env vars:

```typescript
// src/rate-limit-config.ts
export interface EndpointLimit {
  capacity: number;
  refillRate: number;
  cost: number;
}

const LIMITS: Record<string, EndpointLimit> = {
  '/api/v1/auth/login':      { capacity: 10,  refillRate: 0.1,  cost: 1 },
  '/api/v1/auth/register':   { capacity: 5,   refillRate: 0.05, cost: 1 },
  '/api/v1/password-reset':  { capacity: 3,   refillRate: 0.03, cost: 1 },
  '/api/v1/send-message':    { capacity: 50,  refillRate: 5,    cost: 1 },
  'default':                  { capacity: 100, refillRate: 10,   cost: 1 },
};

export function limitForPath(pathname: string): EndpointLimit {
  return LIMITS[pathname] ?? LIMITS['default'];
}

// Include endpoint in the bucket key so limits are scoped per endpoint
export function endpointBucketKey(
  clientKey: string,
  pathname: string
): string {
  return `${clientKey}:${pathname}`;
}
```

---

## Alarm-Based Bucket Expiry

Inactive clients accumulate DO instances. Use the Alarms API to delete idle buckets:

```typescript
// Inside TokenBucket class
async fetch(request: Request): Promise<Response> {
  // ... existing logic ...

  // Schedule expiry: if no request arrives in 1 hour, delete storage
  await this.state.storage.setAlarm(Date.now() + 60 * 60 * 1000);

  return Response.json(result);
}

async alarm(): Promise<void> {
  // DO instance will be garbage-collected after storage is cleared
  await this.state.storage.deleteAll();
}
```

---

## Anti-patterns

**Using KV for token state.** KV is eventually consistent; two Workers can read the same stale value, both compute `tokens >= cost`, and both decrement — granting one extra request. Use Durable Objects or `idFromName` to enforce a single-writer.

**Ignoring the `blockConcurrencyWhile` initialiser.** Without it, two requests hitting a cold DO simultaneously can both start before storage is loaded. The constructor's `blockConcurrencyWhile` ensures initialisation completes before any `fetch` handler runs.

**Using `Date.now()` differences across DO instances for synchronisation.** Each DO instance maintains its own clock. Do not compare timestamps across different DO instances; compute refill using only `Date.now()` within the same instance.

**Making the bucket key too broad.** A single global bucket for all IPs throttles all users together. Scope buckets to the smallest meaningful client identity: authenticated user ID, then IP, never a shared pool.

**Forgetting to set alarms.** Without alarm-based expiry, a DO instance per IP per day accumulates indefinitely. Always schedule an alarm to clean up idle instances.

**Returning 429 without `Retry-After`.** RFC 6585 §4 requires `Retry-After` on 429 responses. Omitting it forces callers to use exponential backoff with no signal about when to retry.

---

## Gotchas

**DO colocated at first request's PoP.** Subsequent requests from a different PoP are routed to the original PoP, adding latency. For global APIs, accept this: the latency (typically <50 ms cross-PoP) is preferable to inconsistent enforcement.

**Storage writes are synchronous within a request.** `storage.put()` inside a DO `fetch` handler commits before the response is returned. There is no way to "roll back" a token deduction if the downstream request fails — design idempotently.

**Hibernation vs. active.** Durable Objects can hibernate when idle. The alarm API wakes a hibernated DO, which re-reads storage — this is correct behaviour. Do not assume in-memory variables survive across requests; always persist to `this.state.storage`.

**DO namespace billing.** Each unique name is a distinct DO instance. A `capacity` of 100 tokens shared across 1 million users means 1 million active DOs. Monitor instance counts via Cloudflare analytics and tune your expiry alarm accordingly.

**`idFromName` is deterministic but not secret.** Anyone who can guess a bucket key name could construct the same DO ID. Never expose DO IDs externally; the rate-limiting call is internal only.

---

## Verification

```bash
# Verify token depletion and 429 with Retry-After
for i in $(seq 1 105); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "CF-Connecting-IP: 203.0.113.1" \
    https://api.example.com/api/v1/send-message)
  echo "Request $i: $STATUS"
done

# Expect 200 for requests 1-100, then 429 for 101-105
# Then wait for refill and verify 200 resumes:
sleep 10
curl -I -H "CF-Connecting-IP: 203.0.113.1" https://api.example.com/api/v1/send-message
# Expect: HTTP/2 200, X-RateLimit-Remaining: <N>

# Verify Retry-After header on 429
curl -v -H "CF-Connecting-IP: 203.0.113.1" https://api.example.com/api/v1/auth/login \
  2>&1 | grep -i 'retry-after'
```

---

## Related

- `rate-limiting-per-user-d1-durable-objects.md` — fixed-window counters using D1
- `cloudflare-rate-limiting-v2-api-abuse-prevention.md` — Cloudflare-managed rate limiting rules
- `durable-objects-auth-patterns.md` — authentication within Durable Objects
- `ddos-mitigation-strategies.md` — layered DDoS defence including rate limiting

---

## Sources

- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- RFC 6585 §4 — Additional HTTP Status Codes (429 Too Many Requests): https://www.rfc-editor.org/rfc/rfc6585#section-4
- Token bucket algorithm: Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §5.3
- Cloudflare Durable Objects Alarms API: https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare `blockConcurrencyWhile`: https://developers.cloudflare.com/durable-objects/api/state/#blockconcurrencywhile
