# Workers Outbound fetch() With No Deadline — 30s Wall-Clock Hang

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A product-enrichment Worker called a third-party pricing API on every request. When the pricing API experienced a brownout, the Worker hung for exactly 30 seconds on each request before returning a 524 (Connection Timeout) to the client. During the incident, all Workers were tied up waiting for the upstream, exhausting the concurrency budget and causing cascading 503s on unrelated routes.

---

## Context

Cloudflare Workers enforce a maximum wall-clock duration of 30 seconds per request (CPU time limit is 50 ms for the free tier, higher for paid). An outbound `fetch()` that connects successfully but receives no response data counts as wall-clock time, not CPU time, so it can silently consume the full 30 seconds. There is no default timeout on `fetch()` in the Workers runtime — it will wait the full 30 seconds unless the caller explicitly provides a signal. During a third-party brownout, every in-flight Worker effectively becomes a zombie waiting on a socket that will never receive bytes.

---

## Root Cause

```typescript
// BAD — no timeout, no fallback
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // If the pricing API hangs, this hangs for up to 30 seconds
    const pricing = await fetch('https://pricing.third-party.io/v2/products', {
      method: 'POST',
      body: JSON.stringify({ ids: getProductIds(request) }),
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.PRICING_KEY}` },
    });

    if (!pricing.ok) {
      return new Response('upstream error', { status: 502 });
    }

    const data = await pricing.json<PricingResponse>();
    return Response.json(enrichProducts(request, data));
  },
};
```

No `signal` is passed to `fetch()`. When the upstream stalls, `await fetch(...)` blocks the Worker's event loop for up to 30 s. Multiply by concurrent requests during a brownout and every Worker instance becomes saturated.

---

## Fix

### 1. Pass `AbortSignal.timeout()` to every outbound fetch

```typescript
// GOOD — 5-second deadline on the upstream call
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let pricing: PricingResponse | null = null;

    try {
      const upstream = await fetch('https://pricing.third-party.io/v2/products', {
        method: 'POST',
        body: JSON.stringify({ ids: getProductIds(request) }),
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${env.PRICING_KEY}`,
        },
        // AbortSignal.timeout is available in Workers runtime >= 2023-03-01
        signal: AbortSignal.timeout(5_000),
      });

      if (upstream.ok) {
        pricing = await upstream.json<PricingResponse>();
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'TimeoutError') {
        console.error('Pricing API timed out after 5 s — using cached fallback');
      } else {
        console.error('Pricing API error:', err);
      }
    }

    // Fallback: serve stale prices from KV when upstream is unavailable
    if (!pricing) {
      pricing = await getCachedPricing(env.PRICING_CACHE, getProductIds(request));
    }

    return Response.json(enrichProducts(request, pricing));
  },
};
```

### 2. KV fallback cache helper

```typescript
async function getCachedPricing(
  kv: KVNamespace,
  ids: string[],
): Promise<PricingResponse | null> {
  const key = `pricing:${ids.sort().join(',')}`;
  const cached = await kv.get<PricingResponse>(key, 'json');
  return cached;
}

async function storeCachedPricing(
  kv: KVNamespace,
  ids: string[],
  data: PricingResponse,
): Promise<void> {
  const key = `pricing:${ids.sort().join(',')}`;
  // TTL: 5 minutes; acceptable staleness for pricing data
  await kv.put(key, JSON.stringify(data), { expirationTtl: 300 });
}
```

### 3. Circuit breaker (optional, for high-traffic routes)

```typescript
// Minimal token-bucket circuit breaker using Durable Objects
type CircuitState = 'closed' | 'open' | 'half-open';

const FAILURE_THRESHOLD = 5;
const OPEN_DURATION_MS = 30_000;

let failures = 0;
let openedAt: number | null = null;

function circuitState(): CircuitState {
  if (failures < FAILURE_THRESHOLD) return 'closed';
  if (openedAt && Date.now() - openedAt > OPEN_DURATION_MS) return 'half-open';
  return 'open';
}

async function fetchWithCircuitBreaker(
  url: string,
  init: RequestInit,
): Promise<Response | null> {
  const state = circuitState();

  if (state === 'open') {
    console.warn('Circuit open — skipping upstream call');
    return null;
  }

  try {
    const res = await fetch(url, { ...init, signal: AbortSignal.timeout(5_000) });
    if (res.ok) {
      failures = 0; // reset on success
      openedAt = null;
    } else {
      failures++;
      if (failures >= FAILURE_THRESHOLD) openedAt = Date.now();
    }
    return res;
  } catch {
    failures++;
    if (failures >= FAILURE_THRESHOLD) openedAt = Date.now();
    return null;
  }
}
```

> Note: in-memory circuit breaker state resets on Worker cold start. For durable circuit state across isolates, persist counters to KV or a Durable Object.

---

## Prevention / Detection

```bash
# Wrangler tail: alert on TimeoutError logs
wrangler tail --env production --format=json \
  | jq 'select(.logs[].message | contains("timed out"))'
```

```typescript
// Integration test: mock upstream that stalls, verify Worker responds < 6 s
import { describe, it, expect } from 'vitest';

describe('pricing fetch with timeout', () => {
  it('falls back to KV within 6 seconds when upstream stalls', async () => {
    // Mock fetch to never resolve
    globalThis.fetch = () => new Promise(() => {}); // infinite hang

    const start = Date.now();
    const response = await workerFetch(new Request('https://example.com/products'));
    const elapsed = Date.now() - start;

    expect(elapsed).toBeLessThan(6_000);
    expect(response.status).toBe(200); // served from KV fallback
  });
});
```

---

## Anti-patterns

- **No signal on outbound fetch** — the Worker is now at the mercy of every upstream server's response time, up to the 30 s wall-clock limit.
- **`Promise.race` with a manual `setTimeout`** — works but is boilerplate; `AbortSignal.timeout()` is idiomatic and cancels the underlying TCP connection, avoiding resource leaks.
- **Treating 502/503 as the only upstream failure mode** — a stalled connection returns no status code at all until the timeout fires; code that only checks `!response.ok` will not handle it.

---

## Gotchas

- `AbortSignal.timeout()` requires `compatibility_date = "2023-03-01"` or later in `wrangler.toml`.
- When the signal fires, `fetch()` throws a `DOMException` with `name === 'TimeoutError'`. Catch specifically on the name to distinguish it from network errors.
- The 5 s timeout chosen here is illustrative; set it based on your upstream's p99 latency SLO, not a round number.
- Caching stale pricing data is a business decision. Coordinate with product and legal before deploying a fallback that may serve out-of-date prices.

---

## Verification

```bash
# 1. Deploy the fixed Worker
wrangler deploy

# 2. Simulate upstream timeout with a slow-responding test server
# (using tc-netem or a netcat listener that never responds)
nc -l 443 &
curl -s 'https://api.example.com/products?ids=a,b,c'
# Should respond in ~5 s with stale/fallback data, not 30 s

# 3. Verify TimeoutError is logged
wrangler tail --format=json | jq 'select(.logs[].message | contains("timed out"))'

# 4. Confirm response time p99 is under 6 s in Workers Analytics
```

---

## Related

- `lessons-workers-cpu-time-exceeded-regex.md`
- `lessons-durable-objects-id-from-name-collision.md`

---

## Sources

- Cloudflare Workers Limits — https://developers.cloudflare.com/workers/platform/limits/
- AbortSignal.timeout() — https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static
- Cloudflare Workers fetch() — https://developers.cloudflare.com/workers/runtime-apis/fetch/
