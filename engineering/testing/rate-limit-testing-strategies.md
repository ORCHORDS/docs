# Rate Limiting and Throttling Testing Strategies

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You implement a rate limiter — 100 requests per minute per user, 10 concurrent requests per IP — and then ship it untested. It works fine in development where single requests are sent at human speed. In production, a legitimate burst of mobile clients hits a flash sale, the limiter fires, and customers see opaque 429 errors. Three months later a penetration tester finds that changing the `X-Forwarded-For` header bypasses the IP-based limit entirely.

Rate limiting and throttling logic is among the most undertested infrastructure code. It has timing dependencies, distributed state (counters in Redis or Durable Objects), and security-critical bypass conditions — exactly the properties that need explicit test strategies.

## Context

Rate limiting manifests at several layers:

| Layer | Example | What to test |
|---|---|---|
| Edge / CDN | Cloudflare Rate Limiting rules | Response code, `Retry-After`, bypass conditions |
| API gateway | Kong, AWS API Gateway | Per-route limits, key extraction |
| Application | Express middleware, Hono middleware | Counter logic, sliding vs fixed window |
| Distributed state | Redis counters, Durable Objects | Atomicity, TTL, race conditions |
| Service-to-service | Internal RPC throttling | Backpressure, circuit breaker coordination |

Testing strategies differ across these layers. This article focuses on unit testing counter logic, integration testing the full middleware stack, and load testing to observe real throttling behaviour under concurrency.

## Unit Testing Counter Logic

Most rate limiters share a core algorithm: increment a counter, compare to a limit, return allow or deny, and set a TTL. Test the algorithm independently of HTTP.

### Fixed Window Rate Limiter

```typescript
// src/rate-limit/fixed-window.ts
export interface RateLimitStore {
  increment(key: string, windowMs: number): Promise<{ count: number; resetAt: number }>;
}

export class FixedWindowRateLimiter {
  constructor(
    private store: RateLimitStore,
    private limit: number,
    private windowMs: number
  ) {}

  async check(key: string): Promise<{ allowed: boolean; remaining: number; resetAt: number }> {
    const { count, resetAt } = await this.store.increment(key, this.windowMs);
    return {
      allowed: count <= this.limit,
      remaining: Math.max(0, this.limit - count),
      resetAt,
    };
  }
}
```

```typescript
// src/rate-limit/fixed-window.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { FixedWindowRateLimiter, RateLimitStore } from './fixed-window';

const makeStore = (): RateLimitStore & { _counts: Map<string, number> } => {
  const counts = new Map<string, number>();
  return {
    _counts: counts,
    async increment(key, windowMs) {
      const current = (counts.get(key) ?? 0) + 1;
      counts.set(key, current);
      return { count: current, resetAt: Date.now() + windowMs };
    },
  };
};

describe('FixedWindowRateLimiter', () => {
  let store: ReturnType<typeof makeStore>;
  let limiter: FixedWindowRateLimiter;

  beforeEach(() => {
    store = makeStore();
    limiter = new FixedWindowRateLimiter(store, 5, 60_000);
  });

  it('allows requests within the limit', async () => {
    for (let i = 0; i < 5; i++) {
      const result = await limiter.check('user:1');
      expect(result.allowed).toBe(true);
    }
  });

  it('denies the request that exceeds the limit', async () => {
    for (let i = 0; i < 5; i++) await limiter.check('user:1');
    const result = await limiter.check('user:1');
    expect(result.allowed).toBe(false);
    expect(result.remaining).toBe(0);
  });

  it('tracks remaining count correctly', async () => {
    const r1 = await limiter.check('user:1');
    expect(r1.remaining).toBe(4);
    const r2 = await limiter.check('user:1');
    expect(r2.remaining).toBe(3);
  });

  it('isolates counters per key', async () => {
    for (let i = 0; i < 5; i++) await limiter.check('user:1');
    const resultUser2 = await limiter.check('user:2');
    expect(resultUser2.allowed).toBe(true);
    expect(resultUser2.remaining).toBe(4);
  });

  it('returns a future resetAt timestamp', async () => {
    const before = Date.now();
    const result = await limiter.check('user:1');
    expect(result.resetAt).toBeGreaterThan(before);
    expect(result.resetAt).toBeLessThanOrEqual(before + 60_000 + 100);
  });
});
```

### Sliding Window Log Algorithm

```typescript
// src/rate-limit/sliding-window.test.ts
import { describe, it, expect, vi } from 'vitest';
import { SlidingWindowRateLimiter } from './sliding-window';

describe('SlidingWindowRateLimiter', () => {
  it('counts only requests within the sliding window', async () => {
    vi.useFakeTimers();
    const store = new InMemorySlidingStore();
    const limiter = new SlidingWindowRateLimiter(store, 3, 60_000);

    const t0 = Date.now();
    await limiter.check('user:1'); // t=0
    vi.advanceTimersByTime(20_000);
    await limiter.check('user:1'); // t=20s
    vi.advanceTimersByTime(20_000);
    await limiter.check('user:1'); // t=40s

    // All 3 are within the 60s window — next should be denied
    const r4 = await limiter.check('user:1');
    expect(r4.allowed).toBe(false);

    // Advance past the first request's window — it should now be pruned
    vi.advanceTimersByTime(25_000); // now t=85s; t=0 request is 85s ago, outside 60s window
    const r5 = await limiter.check('user:1');
    expect(r5.allowed).toBe(true);

    vi.useRealTimers();
  });
});
```

## Integration Testing: HTTP Middleware

Test the rate limiter as mounted in your HTTP framework to verify header output, status codes, and key extraction.

### Hono + Cloudflare Workers Example

```typescript
// src/middleware/rate-limit.integration.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { Hono } from 'hono';
import { createRateLimitMiddleware } from './rate-limit';
import { InMemoryStore } from '../rate-limit/in-memory-store';

function buildApp(limit: number, windowMs: number) {
  const store = new InMemoryStore();
  const app = new Hono();
  app.use('*', createRateLimitMiddleware({ store, limit, windowMs, keyFn: c => c.req.header('x-user-id') ?? 'anon' }));
  app.get('/hello', c => c.text('ok'));
  return app;
}

describe('rate limit middleware', () => {
  let app: Hono;

  beforeEach(() => {
    app = buildApp(3, 60_000);
  });

  async function hit(userId: string) {
    return app.request('/hello', { headers: { 'x-user-id': userId } });
  }

  it('returns 200 while under limit', async () => {
    const res = await hit('u1');
    expect(res.status).toBe(200);
  });

  it('sets X-RateLimit-* headers', async () => {
    const res = await hit('u1');
    expect(res.headers.get('X-RateLimit-Limit')).toBe('3');
    expect(res.headers.get('X-RateLimit-Remaining')).toBe('2');
    expect(res.headers.get('X-RateLimit-Reset')).toBeTruthy();
  });

  it('returns 429 after limit is exceeded', async () => {
    await hit('u2'); await hit('u2'); await hit('u2');
    const res = await hit('u2');
    expect(res.status).toBe(429);
  });

  it('includes Retry-After on 429 response', async () => {
    await hit('u3'); await hit('u3'); await hit('u3');
    const res = await hit('u3');
    const retryAfter = res.headers.get('Retry-After');
    expect(retryAfter).toBeTruthy();
    expect(Number(retryAfter)).toBeGreaterThan(0);
  });

  it('returns 429 body as JSON with error description', async () => {
    await hit('u4'); await hit('u4'); await hit('u4');
    const res = await hit('u4');
    const body = await res.json<{ error: string }>();
    expect(body.error).toMatch(/rate limit/i);
  });

  it('uses separate counters per user', async () => {
    await hit('a'); await hit('a'); await hit('a');
    const resB = await hit('b');
    expect(resB.status).toBe(200);
  });
});
```

## Testing Bypass Attack Vectors

Rate limiters are security controls. Test the attack surface explicitly.

```typescript
// src/middleware/rate-limit.security.test.ts
import { describe, it, expect } from 'vitest';

describe('rate limit bypass resistance', () => {
  it('does not trust X-Forwarded-For when extracting IP key', async () => {
    const app = buildIpBasedApp(3, 60_000);

    // Exhaust limit for the true client IP (simulated by cf-connecting-ip)
    for (let i = 0; i < 3; i++) {
      await app.request('/hello', {
        headers: { 'cf-connecting-ip': '1.2.3.4' },
      });
    }

    // Attacker tries to spoof a different IP via X-Forwarded-For
    const res = await app.request('/hello', {
      headers: {
        'cf-connecting-ip': '1.2.3.4',   // true IP — still limited
        'x-forwarded-for': '9.9.9.9',    // spoof — should be ignored
      },
    });
    expect(res.status).toBe(429); // Must still be rate limited
  });

  it('normalises key case to prevent case-based bypass', async () => {
    const app = buildUserIdApp(3, 60_000);
    await app.request('/hello', { headers: { 'x-user-id': 'User-123' } });
    await app.request('/hello', { headers: { 'x-user-id': 'User-123' } });
    await app.request('/hello', { headers: { 'x-user-id': 'User-123' } });

    // Attempt bypass by sending different case
    const res = await app.request('/hello', { headers: { 'x-user-id': 'user-123' } });
    // Keys must be normalised to lowercase; this should be limited
    expect(res.status).toBe(429);
  });

  it('applies a fallback key for unauthenticated requests', async () => {
    const app = buildUserIdApp(3, 60_000);
    // No x-user-id header — should not throw but use a fallback key
    const res = await app.request('/hello', {});
    expect(res.status).not.toBe(500);
  });
});
```

## Load Testing to Observe Real Throttling Behaviour

Unit tests verify the logic. Load tests verify it holds under actual concurrency with a real Redis/Durable Object backend.

### k6 Script for Rate Limit Verification

```javascript
// load-tests/rate-limit-check.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const denied = new Counter('rate_limited_requests');
const allowed = new Counter('allowed_requests');

export const options = {
  // Burst 20 VUs for 10 seconds — should trigger limiting
  scenarios: {
    burst: {
      executor: 'constant-vus',
      vus: 20,
      duration: '10s',
    },
  },
  thresholds: {
    // At least some requests must be rate limited — confirms the limiter is active
    rate_limited_requests: ['count>0'],
    // Some requests must succeed — confirms the limiter is not blocking everything
    allowed_requests: ['count>0'],
    // No 5xx errors — the limiter must not crash the service
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const res = http.get('https://api.example.com/v1/data', {
    headers: { 'X-User-Id': `user-${Math.floor(Math.random() * 5)}` },
  });

  if (res.status === 429) {
    denied.add(1);
    check(res, {
      'has Retry-After header': r => !!r.headers['Retry-After'],
      'has X-RateLimit-Reset header': r => !!r.headers['X-RateLimit-Reset'],
    });
  } else if (res.status === 200) {
    allowed.add(1);
    check(res, {
      'has X-RateLimit-Remaining header': r => !!r.headers['X-RateLimit-Remaining'],
    });
  }
}
```

### Cloudflare Durable Objects Atomicity Test

When your rate limiter uses a Durable Object for atomic counter updates, a concurrent-request unit test verifies no race condition exists:

```typescript
// src/rate-limit/do-counter.test.ts
import { env, SELF } from 'cloudflare:test';
import { it, expect } from 'vitest';

it('does not exceed the limit under concurrent requests', async () => {
  const LIMIT = 5;
  const requests = Array.from({ length: 10 }, () =>
    SELF.fetch('https://example.com/api/data', {
      headers: { 'x-user-id': 'concurrent-user' },
    })
  );

  const responses = await Promise.all(requests);
  const statuses = responses.map(r => r.status);

  const allowed = statuses.filter(s => s === 200).length;
  const denied = statuses.filter(s => s === 429).length;

  // Exactly LIMIT requests should succeed; the rest are denied
  expect(allowed).toBe(LIMIT);
  expect(denied).toBe(10 - LIMIT);
});
```

## Anti-patterns

- **Only testing the "happy path"** — verifying that allowed requests go through is not enough. Explicitly test the exact boundary (limit-1, limit, limit+1) and the 429 response format.
- **Resetting the store between tests using `beforeEach` sleep** — `sleep(windowMs)` in tests makes the suite slow and fragile. Use fake timers or design the store to accept an injectable clock.
- **Trusting `X-Forwarded-For` for IP-based limiting** — always use the authoritative IP header for your infrastructure (`CF-Connecting-IP` on Cloudflare, `X-Real-IP` from nginx with `real_ip_from` set). Document which header you trust and test bypass attempts.
- **Not testing the `Retry-After` value** — clients use this header to implement exponential backoff. A wrong value (0, negative, or missing) causes clients to hammer the endpoint immediately.
- **Testing rate limiting with `Date.now()` without mocking time** — fixed-window boundaries depend on wall-clock time. Use `vi.useFakeTimers()` or an injectable `Clock` interface to make window transitions deterministic.

## Gotchas

- **Redis INCR + EXPIRE race** — `INCR key` then `EXPIRE key ttl` is two commands; if the process crashes between them, the key never expires. Use `SET key 0 EX ttl NX` + `INCR key` or Lua scripts for atomic increment-with-TTL. Test this by simulating a crash between the two operations.
- **Durable Object single-threaded writes** — Durable Objects serialize writes, so concurrent requests to the same DO instance queue up. This prevents race conditions but adds latency. Load test to confirm the queuing behaviour under your peak concurrency.
- **`Promise.all` in tests does not guarantee true concurrency** — JavaScript is single-threaded; `Promise.all` sends all requests in the same event loop tick but the server processes them sequentially if it's also running in the same process. For true concurrency tests, use a real HTTP server and k6 or Artillery.
- **Rate limit key collisions** — if your key is `ip:user_id` and you have many anonymous requests, all anonymous traffic shares one counter. Understand your key space before setting limits.

## Verification

```bash
# Unit tests
npx vitest run src/rate-limit/

# Integration tests
npx vitest run src/middleware/rate-limit.integration.test.ts

# Security tests
npx vitest run src/middleware/rate-limit.security.test.ts

# Load test (against a local server)
PORT=3000 npm run start &
k6 run --env BASE_URL=http://localhost:3000 load-tests/rate-limit-check.js
```

Confirm:
- The 429 response is returned at exactly `limit + 1` requests, not at `limit` or `limit + 2`.
- `X-RateLimit-Remaining` decrements correctly from `limit - 1` to `0`.
- The load test shows `rate_limited_requests` counter > 0 and no 5xx responses.
- Spoofing `X-Forwarded-For` does not bypass an IP-based limit.

## Related

- `performance-testing-k6.md`
- `k6-load-testing-cloudflare-workers-api.md`
- `chaos-engineering-cloudflare-workers.md`
- `resilience-circuit-breaker-testing.md`
- `idempotency-retry-safety-testing.md`
- `security-testing-automation-pipeline.md`

## Sources

- IETF RFC 6585 — 429 Too Many Requests: https://datatracker.ietf.org/doc/html/rfc6585
- IETF RFC 7231 — Retry-After header: https://datatracker.ietf.org/doc/html/rfc7231#section-7.1.3
- Cloudflare Rate Limiting documentation: https://developers.cloudflare.com/waf/rate-limiting-rules/
- Redis rate limiting patterns: https://redis.io/docs/manual/patterns/distributed-locks/
- k6 custom metrics: https://grafana.com/docs/k6/latest/using-k6/metrics/create-custom-metrics/
- OWASP API Security Top 10 — API4: Unrestricted Resource Consumption: https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/
