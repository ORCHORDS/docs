# Scatter-Gather Pattern: Parallel Upstream Fetching in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker needs data from three upstream APIs — pricing service, inventory service, and user-profile service — to compose a single response. Called sequentially, the total latency is the sum of all upstream latencies. With a 200 ms budget and three 100 ms upstreams, you miss the SLA by 200 ms.

You need to fan out requests in parallel, collect results, tolerate partial failures, and return a merged response within the time budget.

---

## Context

Cloudflare Workers run on V8 isolates. Concurrent `fetch()` calls are genuinely parallel at the I/O layer — the Worker is not blocked while awaiting network responses. This makes Workers an ideal scatter-gather aggregator.

The pattern:
1. **Scatter** — dispatch N sub-requests concurrently.
2. **Gather** — collect all results (fulfilled or rejected) via `Promise.allSettled`.
3. **Merge** — aggregate, apply error budget, return composite response.

Suitable when:
- Response requires data from multiple independent upstreams.
- Upstreams can be queried in parallel (no data dependency between them).
- Partial results are acceptable if within an error budget.

---

## Solution

```typescript
// aggregator/src/index.ts
export interface Env {
  PRICING_SERVICE_URL: string;
  INVENTORY_SERVICE_URL: string;
  PROFILE_SERVICE_URL: string;
}

interface PricingResult {
  sku: string;
  priceCents: number;
  currency: string;
}

interface InventoryResult {
  sku: string;
  available: boolean;
  quantity: number;
}

interface ProfileResult {
  userId: string;
  tier: 'free' | 'pro' | 'enterprise';
  discountBps: number; // basis points
}

interface AggregatedProductResponse {
  sku: string;
  userId: string;
  pricing: PricingResult | null;
  inventory: InventoryResult | null;
  profile: ProfileResult | null;
  degraded: boolean;
  missingUpstreams: string[];
}

// Per-upstream timeout in milliseconds
const UPSTREAM_TIMEOUT_MS = 800;

// Maximum fraction of upstreams allowed to fail before the entire response is rejected
const ERROR_BUDGET_RATIO = 0.5; // 50% — at least half must succeed

async function fetchWithTimeout<T>(
  url: string,
  label: string,
  timeoutMs: number,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`${label} returned HTTP ${response.status}`);
    }
    return await response.json() as T;
  } finally {
    clearTimeout(timer);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const sku = url.searchParams.get('sku');
    const userId = url.searchParams.get('userId');

    if (!sku || !userId) {
      return new Response(JSON.stringify({ error: 'sku and userId required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // --- SCATTER ---
    const [pricingSettled, inventorySettled, profileSettled] = await Promise.allSettled([
      fetchWithTimeout<PricingResult>(
        `${env.PRICING_SERVICE_URL}/price?sku=${sku}`,
        'pricing',
        UPSTREAM_TIMEOUT_MS,
      ),
      fetchWithTimeout<InventoryResult>(
        `${env.INVENTORY_SERVICE_URL}/inventory?sku=${sku}`,
        'inventory',
        UPSTREAM_TIMEOUT_MS,
      ),
      fetchWithTimeout<ProfileResult>(
        `${env.PROFILE_SERVICE_URL}/profile?userId=${userId}`,
        'profile',
        UPSTREAM_TIMEOUT_MS,
      ),
    ]);

    // --- GATHER ---
    const upstreamResults = [
      { label: 'pricing', settled: pricingSettled },
      { label: 'inventory', settled: inventorySettled },
      { label: 'profile', settled: profileSettled },
    ];

    const failedUpstreams = upstreamResults
      .filter((r) => r.settled.status === 'rejected')
      .map((r) => r.label);

    const failureRatio = failedUpstreams.length / upstreamResults.length;

    // Log individual failures for observability
    for (const { label, settled } of upstreamResults) {
      if (settled.status === 'rejected') {
        console.error(JSON.stringify({
          type: 'upstream_failure',
          upstream: label,
          error: settled.reason instanceof Error ? settled.reason.message : String(settled.reason),
        }));
      }
    }

    // Error budget check — fail hard if too many upstreams are down
    if (failureRatio > ERROR_BUDGET_RATIO) {
      return new Response(
        JSON.stringify({
          error: 'too_many_upstream_failures',
          failed: failedUpstreams,
          failureRatio,
        }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      );
    }

    // --- MERGE ---
    const pricing = pricingSettled.status === 'fulfilled' ? pricingSettled.value : null;
    const inventory = inventorySettled.status === 'fulfilled' ? inventorySettled.value : null;
    const profile = profileSettled.status === 'fulfilled' ? profileSettled.value : null;

    const aggregated: AggregatedProductResponse = {
      sku,
      userId,
      pricing: pricing ? applyDiscount(pricing, profile?.discountBps ?? 0) : null,
      inventory,
      profile,
      degraded: failedUpstreams.length > 0,
      missingUpstreams: failedUpstreams,
    };

    const statusCode = aggregated.degraded ? 206 : 200; // 206 Partial Content when degraded

    return new Response(JSON.stringify(aggregated), {
      status: statusCode,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};

function applyDiscount(pricing: PricingResult, discountBps: number): PricingResult {
  if (discountBps === 0) return pricing;
  const discounted = Math.round(pricing.priceCents * (1 - discountBps / 10_000));
  return { ...pricing, priceCents: discounted };
}
```

### Stale-while-revalidate layer (optional)

```typescript
// Cache a previous good result and serve it during upstream degradation
async function fetchWithFallback<T>(
  kv: KVNamespace,
  cacheKey: string,
  fetcher: () => Promise<T>,
  ttlSeconds: number,
): Promise<{ value: T; stale: boolean }> {
  try {
    const fresh = await fetcher();
    // Best-effort cache write — do not await to avoid adding latency
    kv.put(cacheKey, JSON.stringify(fresh), { expirationTtl: ttlSeconds });
    return { value: fresh, stale: false };
  } catch {
    const cached = await kv.get<T>(cacheKey, 'json');
    if (cached !== null) {
      return { value: cached, stale: true };
    }
    throw new Error(`No data for ${cacheKey} — upstream down and no cache`);
  }
}
```

---

## Implementation Details

**`Promise.allSettled` vs `Promise.all`:** Use `allSettled` for scatter-gather. `Promise.all` short-circuits on the first rejection, aborting all in-flight requests. `allSettled` waits for all and provides per-promise status, enabling partial-result handling.

**Per-upstream timeouts:** Use `AbortController` with individual timers per upstream. A single global timeout aborts all upstreams if any one is slow; per-upstream timeouts allow each to have a different SLA.

**Response status 206:** Returning HTTP 206 Partial Content for degraded aggregations is a clear contract signal to API clients that the response is incomplete. Clients can decide whether to retry, display a fallback, or proceed.

**Subrequest limits:** Cloudflare Workers allow up to 1,000 subrequests per invocation. For fan-outs exceeding ~50 upstreams, consider batching scatter rounds.

**Context propagation:** Forward `X-Request-Id` and `traceparent` headers into each upstream request for distributed tracing.

---

## Anti-patterns

- **Sequential await in a loop:** `for (const url of urls) { await fetch(url); }` serialises requests. Use `Promise.allSettled(urls.map(fetchFn))` to parallelise.
- **Global timeout wrapping `Promise.allSettled`:** A single outer `AbortController` aborts all sub-requests simultaneously when the slowest one triggers the timeout. Per-upstream timeouts are more surgical.
- **Zero tolerance for partial failure:** Requiring all N upstreams to succeed makes your availability the product of all upstream availabilities (e.g., 99% × 99% × 99% = 97%). Define an explicit error budget.
- **Returning 200 on a degraded response without signalling:** Clients silently consume incomplete data. Use 206 or a `degraded` flag.

---

## Gotchas

- Workers have a CPU time limit (10 ms free, 30 s paid) but I/O wait time does not count against the CPU limit. Parallel fetches add zero CPU time while waiting.
- `AbortController.abort()` in Workers cancels the outgoing `fetch()` but does not interrupt server-side processing at the upstream. The upstream will still complete its work.
- `Promise.allSettled` resolves when all promises settle, meaning total wall-clock time equals the slowest upstream, not the sum. Ensure the slowest upstream's timeout fits within the Worker's request wall-clock limit.
- Do not cache KV writes inside `waitUntil()` if the Worker has already returned a response — the event loop may be torn down before the write completes on cold edge nodes.

---

## Verification

1. Mock all three upstreams with 100 ms latency each. Total response time should be ~100 ms, not 300 ms.
2. Inject a 2-second delay into one upstream. Confirm it times out at `UPSTREAM_TIMEOUT_MS` and the response is 206 with `degraded: true`.
3. Take two upstreams down. Confirm the error budget triggers a 503.
4. Verify `X-Request-Id` appears in the logs of all three upstream mocks for a single Worker request.

---

## Related

- `workers-read-through-cache-pattern-kv.md` — caching upstream results to reduce scatter frequency
- `workers-bulkhead-pattern-queue-isolation.md` — isolating upstream failure domains for async work
- Cloudflare Workers fetch limits: https://developers.cloudflare.com/workers/platform/limits/#fetch-api

---

## Sources

- Enterprise Integration Patterns — Hohpe & Woolf, Chapter 7: Scatter-Gather
- MDN: Promise.allSettled — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/allSettled
- Cloudflare Workers: Fetch API — https://developers.cloudflare.com/workers/runtime-apis/fetch/
