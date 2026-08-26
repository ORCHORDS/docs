# Token Bucket Rate Limiting with Workers KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your API is getting hammered by bursts of requests from individual users or IPs, and you need smooth, per-entity rate limiting without a centralised database. You want to allow short bursts while still enforcing a sustained throughput cap, and return RFC-standard `429` responses with a meaningful `X-RateLimit-Reset` header.

---

## Context

The token bucket algorithm models each user's allowance as a bucket that refills at a fixed rate up to a maximum capacity. Each request consumes one token; if the bucket is empty the request is rejected. Cloudflare Workers KV is an eventually-consistent key-value store with global replication — it suits this pattern because rate-limit state is short-lived, slightly stale reads are acceptable in high-concurrency bursts, and KV's `getWithMetadata` + conditional `put` gives an optimistic-lock primitive. The bucket state `{ tokens, lastRefill }` is stored under a key derived from the entity (user ID or IP). On every request the Worker reads the bucket, refills tokens proportional to elapsed time, consumes one token, and writes the updated state back. When tokens are exhausted the Worker returns a `429` with `Retry-After` and `X-RateLimit-Reset` headers computed from the refill rate.

---

## KV Namespace Setup

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id     = "<your-kv-namespace-id>"
preview_id = "<your-preview-kv-namespace-id>"

[vars]
BUCKET_CAPACITY  = "20"   # max tokens in bucket
REFILL_RATE      = "10"   # tokens added per second
BUCKET_TTL_SEC   = "60"   # KV expiration for idle buckets
```

---

## Implementation

```typescript
// src/rate-limit.ts

export interface Env {
  RATE_LIMIT_KV: KVNamespace;
  BUCKET_CAPACITY: string;
  REFILL_RATE: string;
  BUCKET_TTL_SEC: string;
}

interface BucketState {
  tokens: number;
  lastRefill: number; // Unix ms
}

/** Derive a bucket key from the request — user-id header takes priority over IP. */
function bucketKey(request: Request): string {
  const userId = request.headers.get("X-User-Id");
  if (userId) return `user:${userId}`;
  const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
  return `ip:${ip}`;
}

/**
 * Attempt to consume one token from the bucket.
 * Returns { allowed: true } or { allowed: false, resetAt: number }.
 */
export async function consumeToken(
  request: Request,
  env: Env
): Promise<{ allowed: true } | { allowed: false; resetAt: number }> {
  const capacity  = parseInt(env.BUCKET_CAPACITY, 10);
  const refillRate = parseFloat(env.REFILL_RATE);   // tokens/second
  const ttlSec    = parseInt(env.BUCKET_TTL_SEC, 10);

  const key = bucketKey(request);
  const now = Date.now();

  // ── Read current state ────────────────────────────────────────────────────
  const existing = await env.RATE_LIMIT_KV.get<BucketState>(key, "json");

  let tokens: number;
  let lastRefill: number;

  if (existing === null) {
    // First request — start with a full bucket minus the token we're about to use
    tokens     = capacity - 1;
    lastRefill = now;

    await env.RATE_LIMIT_KV.put(
      key,
      JSON.stringify({ tokens, lastRefill }),
      { expirationTtl: ttlSec }
    );
    return { allowed: true };
  }

  // ── Refill tokens based on elapsed time ──────────────────────────────────
  const elapsedSec = (now - existing.lastRefill) / 1_000;
  tokens = Math.min(capacity, existing.tokens + elapsedSec * refillRate);
  lastRefill = now;

  // ── Consume one token ────────────────────────────────────────────────────
  if (tokens < 1) {
    const secondsUntilToken = (1 - tokens) / refillRate;
    const resetAt = Math.ceil(now / 1_000 + secondsUntilToken);
    return { allowed: false, resetAt };
  }

  tokens -= 1;

  // ── Write back (best-effort, KV is eventually consistent) ────────────────
  await env.RATE_LIMIT_KV.put(
    key,
    JSON.stringify({ tokens, lastRefill }),
    { expirationTtl: ttlSec }
  );

  return { allowed: true };
}

// src/index.ts
import { consumeToken, type Env } from "./rate-limit";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const result = await consumeToken(request, env);

    if (!result.allowed) {
      return new Response("Too Many Requests", {
        status: 429,
        headers: {
          "Retry-After":       String(result.resetAt - Math.floor(Date.now() / 1_000)),
          "X-RateLimit-Reset": String(result.resetAt),
          "Content-Type":      "text/plain",
        },
      });
    }

    // ── Normal request handling ────────────────────────────────────────────
    return new Response("OK", { status: 200 });
  },
};
```

---

## Integration / Testing

```typescript
// test/rate-limit.test.ts  (Vitest + @cloudflare/vitest-pool-workers)
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import worker from "../src/index";

describe("token bucket rate limiter", () => {
  const makeRequest = () =>
    new Request("https://api.example.com/data", {
      headers: { "X-User-Id": "user-42", "CF-Connecting-IP": "1.2.3.4" },
    });

  beforeEach(async () => {
    // Reset KV between tests
    const keys = await env.RATE_LIMIT_KV.list();
    await Promise.all(keys.keys.map((k) => env.RATE_LIMIT_KV.delete(k.name)));
  });

  it("allows requests within capacity", async () => {
    const ctx = createExecutionContext();
    const res = await worker.fetch(makeRequest(), env, ctx);
    await waitOnExecutionContext(ctx);
    expect(res.status).toBe(200);
  });

  it("returns 429 after bucket exhaustion", async () => {
    const capacity = parseInt(env.BUCKET_CAPACITY, 10);
    for (let i = 0; i < capacity; i++) {
      const ctx = createExecutionContext();
      await worker.fetch(makeRequest(), env, ctx);
      await waitOnExecutionContext(ctx);
    }
    const ctx = createExecutionContext();
    const res = await worker.fetch(makeRequest(), env, ctx);
    await waitOnExecutionContext(ctx);
    expect(res.status).toBe(429);
    expect(res.headers.get("X-RateLimit-Reset")).toBeTruthy();
  });
});
```

---

## Anti-patterns

- **Global counter in KV** — a single counter with no per-user key causes all users to share one bucket; first caller blocks everyone else.
- **Skipping the refill step** — decrementing a counter without adding tokens over time turns the algorithm into a fixed-window counter, losing the burst-smoothing property.
- **Using `waitUntil` for the KV write** — deferring the write means two simultaneous requests can both read the same stale state and both succeed, undercounting consumption.
- **Too-short `expirationTtl`** — if the TTL is shorter than the refill window, idle users regain a phantom full bucket every TTL cycle, defeating sustained-rate enforcement.

---

## Gotchas

- KV is eventually consistent; under extreme concurrency two requests can read the same bucket value. For strict accuracy use a Durable Object instead (see `request-coalescing-durable-objects.md`).
- `CF-Connecting-IP` is only populated on routes with a real client; in Wrangler dev it is absent — add a fallback for local testing.
- `expirationTtl` must be at least 60 seconds per KV API limits; use a higher value for slow-refill buckets.
- Floating-point tokens (`tokens + elapsedSec * refillRate`) can accumulate tiny rounding errors — cap with `Math.min(capacity, ...)` on every read.

---

## Verification

```bash
# Deploy and smoke-test locally
npx wrangler dev &

# First 20 requests should return 200
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-User-Id: test-user" \
    http://localhost:8787/
done

# 21st request should return 429
curl -i -H "X-User-Id: test-user" http://localhost:8787/
# Look for: HTTP/1.1 429 and X-RateLimit-Reset header

# Inspect bucket state in KV
npx wrangler kv key get --binding=RATE_LIMIT_KV "user:test-user"
```

---

## Related

- `request-coalescing-durable-objects.md`
- `write-behind-cache-workers-kv-d1.md`

---

## Sources

- Cloudflare Workers KV API — https://developers.cloudflare.com/kv/api/
- Token bucket algorithm — https://en.wikipedia.org/wiki/Token_bucket
- Cloudflare rate limiting patterns — https://developers.cloudflare.com/workers/examples/rate-limiting/
