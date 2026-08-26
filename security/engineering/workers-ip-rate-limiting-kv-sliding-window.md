# IP-Based Rate Limiting with KV Sliding Window Algorithm

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker API is experiencing abusive traffic from individual IP addresses — credential stuffing, scraping, or denial-of-service — and you need a configurable rate limit that counts only requests within a rolling time window rather than a fixed bucket reset. A sliding-window counter stored in Cloudflare KV gives per-IP granularity with sub-millisecond overhead per request and automatic expiry of stale data via KV TTL.

---

## Context

Fixed-window counters (e.g. reset at the top of each minute) are vulnerable to burst exploitation at window boundaries: an attacker can send the full limit at the end of one window and the full limit at the start of the next, doubling the effective burst. The sliding-window algorithm avoids this by storing each request's timestamp in an array under a KV key derived from the client IP; on each request the Worker trims timestamps older than the window duration before counting. Cloudflare sets `cf.connectingIP` (or `X-Forwarded-For` behind a proxy) to the client IP. A bypass list stored in KV allows trusted IPs (monitoring services, internal load balancers) to skip limiting. Standard rate-limit response headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`) give well-behaved clients the information they need to back off gracefully.

---

## Section 1 — Wrangler Config / KV Binding

```toml
# wrangler.toml
name            = "rate-limited-api"
main            = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
RATE_LIMIT        = "100"          # requests per window
RATE_WINDOW_SEC   = "60"           # sliding window in seconds

[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id      = "<your-kv-namespace-id>"

# KV key for bypass list: "bypass_list" → JSON array of IP strings
# e.g. wrangler kv key put --binding RATE_LIMIT_KV bypass_list '["1.2.3.4","10.0.0.1"]'
```

---

## Section 2 — Worker Implementation

```typescript
// src/rate-limit.ts

export interface RateLimitConfig {
  limit: number;
  windowSec: number;
}

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;   // Unix timestamp (seconds) when the oldest entry expires
  retryAfter: number; // seconds
}

function kvKeyForIp(ip: string): string {
  // Sanitise IP to produce a valid KV key (max 512 bytes, no control chars)
  return `rl:${ip.replace(/[^a-zA-Z0-9.:_-]/g, '_')}`;
}

export async function checkRateLimit(
  ip: string,
  kv: KVNamespace,
  config: RateLimitConfig,
): Promise<RateLimitResult> {
  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - config.windowSec;
  const key = kvKeyForIp(ip);

  // Fetch existing timestamps for this IP
  const raw = await kv.get(key);
  let timestamps: number[] = raw ? (JSON.parse(raw) as number[]) : [];

  // Slide: remove entries outside the window
  timestamps = timestamps.filter((ts) => ts > windowStart);

  const count = timestamps.length;
  const allowed = count < config.limit;

  if (allowed) {
    // Record this request
    timestamps.push(now);
    // TTL = window length so KV auto-expires stale keys
    await kv.put(key, JSON.stringify(timestamps), { expirationTtl: config.windowSec });
  }

  const oldest = timestamps.length > 0 ? timestamps[0] : now;
  const resetAt = oldest + config.windowSec;

  return {
    allowed,
    remaining: Math.max(0, config.limit - timestamps.length),
    resetAt,
    retryAfter: allowed ? 0 : resetAt - now,
  };
}

export async function isBypassedIp(ip: string, kv: KVNamespace): Promise<boolean> {
  const raw = await kv.get('bypass_list');
  if (!raw) return false;
  try {
    const list = JSON.parse(raw) as string[];
    return list.includes(ip);
  } catch {
    return false;
  }
}
```

```typescript
// src/index.ts
import { checkRateLimit, isBypassedIp, type RateLimitConfig } from './rate-limit';

export interface Env {
  RATE_LIMIT_KV: KVNamespace;
  RATE_LIMIT: string;
  RATE_WINDOW_SEC: string;
}

function getClientIp(request: Request): string {
  // Cloudflare sets CF-Connecting-IP; fall back to X-Forwarded-For
  return (
    request.headers.get('CF-Connecting-IP') ??
    (request.headers.get('X-Forwarded-For') ?? '').split(',')[0].trim() ??
    'unknown'
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ip = getClientIp(request);
    const config: RateLimitConfig = {
      limit: parseInt(env.RATE_LIMIT, 10),
      windowSec: parseInt(env.RATE_WINDOW_SEC, 10),
    };

    // Check bypass list first to skip KV write for trusted IPs
    const bypassed = await isBypassedIp(ip, env.RATE_LIMIT_KV);
    if (!bypassed) {
      const result = await checkRateLimit(ip, env.RATE_LIMIT_KV, config);
      const rateLimitHeaders: Record<string, string> = {
        'X-RateLimit-Limit': String(config.limit),
        'X-RateLimit-Remaining': String(result.remaining),
        'X-RateLimit-Reset': String(result.resetAt),
      };

      if (!result.allowed) {
        return new Response('Too Many Requests', {
          status: 429,
          headers: {
            ...rateLimitHeaders,
            'Retry-After': String(result.retryAfter),
            'Content-Type': 'text/plain',
          },
        });
      }

      // Attach rate-limit headers to the normal response path
      const downstream = await handleRequest(request);
      const headers = new Headers(downstream.headers);
      for (const [k, v] of Object.entries(rateLimitHeaders)) {
        headers.set(k, v);
      }
      return new Response(downstream.body, {
        status: downstream.status,
        statusText: downstream.statusText,
        headers,
      });
    }

    return handleRequest(request);
  },
};

async function handleRequest(_request: Request): Promise<Response> {
  return new Response(JSON.stringify({ ok: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## Section 3 — Testing / Verification

```typescript
// test/rate-limit.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { env } from 'cloudflare:test';
import { checkRateLimit } from '../src/rate-limit';

describe('sliding window rate limit', () => {
  beforeEach(async () => {
    // Clear KV state between tests
    await env.RATE_LIMIT_KV.delete('rl:192.168.1.1');
  });

  it('allows requests under the limit', async () => {
    const config = { limit: 5, windowSec: 60 };
    for (let i = 0; i < 5; i++) {
      const result = await checkRateLimit('192.168.1.1', env.RATE_LIMIT_KV, config);
      expect(result.allowed).toBe(true);
    }
  });

  it('blocks the request that exceeds the limit', async () => {
    const config = { limit: 3, windowSec: 60 };
    for (let i = 0; i < 3; i++) {
      await checkRateLimit('192.168.1.1', env.RATE_LIMIT_KV, config);
    }
    const blocked = await checkRateLimit('192.168.1.1', env.RATE_LIMIT_KV, config);
    expect(blocked.allowed).toBe(false);
    expect(blocked.remaining).toBe(0);
    expect(blocked.retryAfter).toBeGreaterThan(0);
  });
});
```

---

## Anti-patterns

- **Using a fixed-window counter** — allows doubling the burst rate at window boundaries; use sliding window timestamps instead.
- **Not setting a KV TTL** — without `expirationTtl`, KV keys accumulate indefinitely; set TTL equal to the window duration so stale keys are automatically removed.
- **Deriving client IP solely from `X-Forwarded-For`** — this header can be spoofed when the request reaches the Worker directly; always prefer `CF-Connecting-IP` which Cloudflare sets authoritatively.
- **Storing rate limit state in a global variable** — Workers isolates are not shared across data centres or even across all requests in a single PoP; global state is per-isolate and unreliable for rate limiting.
- **Blocking the response while writing to KV** — use `ctx.waitUntil(kv.put(...))` for non-critical writes to avoid adding KV write latency to the response time.

---

## Gotchas

- KV consistency is eventual; a burst of concurrent requests may all read a stale count simultaneously and each be allowed. For strict enforcement consider Durable Objects which provide strong consistency.
- KV `expirationTtl` minimum is 60 seconds; if your window is shorter than 60 seconds, entries will live longer than the window — adjust the filter logic accordingly.
- The `bypass_list` KV key is read on every non-bypassed request; cache it in module scope with a short TTL (e.g. 30 seconds) to avoid the extra KV read on the hot path.
- IPv6 addresses contain colons; `kvKeyForIp` sanitises them, but ensure the sanitised key does not collide between `::1` and `0:0:0:0:0:0:0:1`.
- `CF-Connecting-IP` returns a single IP string; `X-Forwarded-For` may return a comma-separated list — always take only the first (leftmost) entry.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Seed bypass list
npx wrangler kv key put --binding RATE_LIMIT_KV bypass_list '["203.0.113.5"]'

# Hammer the endpoint to trigger rate limiting (adjust URL)
for i in $(seq 1 110); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://rate-limited-api.<subdomain>.workers.dev/)
  echo "Request $i: $STATUS"
done
# Expect: first 100 return 200, subsequent return 429

# Inspect rate-limit headers on a successful response
curl -i https://rate-limited-api.<subdomain>.workers.dev/ | grep -i x-ratelimit

# Unit tests
npx vitest run
```

---

## Related

- `workers-jwt-rs256-verification-webcrypto.md`
- `workers-secrets-rotation-zero-downtime.md`

---

## Sources

- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare Rate Limiting (managed) — https://developers.cloudflare.com/waf/rate-limiting-rules/
- Sliding Window Rate Limiting Algorithm — https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
- Cloudflare Durable Objects (for strong consistency) — https://developers.cloudflare.com/durable-objects/
