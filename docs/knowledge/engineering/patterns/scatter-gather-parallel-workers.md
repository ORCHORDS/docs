# Scatter-Gather Pattern with Parallel Workers Subrequests

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

A single API response needs data from several independent sources: a pricing
service, an inventory service, a reviews aggregator, and a shipping-estimate
service. Calling them sequentially inflates latency by the sum of all upstream
response times. You need to call them in parallel and merge results before
responding to the client.

---

## Context

The **scatter-gather** pattern fans out a request to N downstream services
simultaneously (scatter), collects all the responses (gather), and combines
them into a single reply. It trades sequential latency for parallel latency,
reducing wall-clock time from O(Σ RTTi) to O(max RTTi).

In Cloudflare Workers this maps directly to:

- **Scatter**: Launch N `fetch()` calls without `await`-ing them individually,
  collecting the resulting `Promise<Response>` objects.
- **Gather**: `Promise.allSettled()` (or `Promise.all()` for fail-fast semantics)
  waits for all promises to settle.
- **Merge**: Inspect each settled result, extract data from fulfilled promises,
  handle rejected ones with defaults or error markers.

Workers imposes a subrequest limit of **1 000 open connections per invocation**
(as of mid-2026). Practical scatter operations should stay well below 50 to
avoid unpredictable fetch scheduling delays in the Worker runtime.

---

## Basic Scatter-Gather

```typescript
// src/handlers/product-detail.ts
import { Env } from '../types';

interface ServiceResult<T> {
  ok: true;
  data: T;
} | {
  ok: false;
  error: string;
}

export async function getProductDetail(
  productId: string,
  env: Env,
): Promise<Response> {
  // --- SCATTER: launch all fetches simultaneously ---
  const [pricePromise, inventoryPromise, reviewsPromise, shippingPromise] = [
    fetchPrice(productId, env),
    fetchInventory(productId, env),
    fetchReviews(productId, env),
    fetchShippingEstimate(productId, env),
  ];

  // --- GATHER: wait for all, capturing individual failures ---
  const [priceResult, inventoryResult, reviewsResult, shippingResult] =
    await Promise.allSettled([
      pricePromise,
      inventoryPromise,
      reviewsPromise,
      shippingPromise,
    ]);

  // --- MERGE: build response, degrading gracefully on partial failures ---
  return Response.json({
    productId,
    price:    settled(priceResult,    null),
    inventory: settled(inventoryResult, { available: false }),
    reviews:  settled(reviewsResult,  { count: 0, average: null }),
    shipping: settled(shippingResult, null),
  });
}

function settled<T>(
  result: PromiseSettledResult<T>,
  fallback: T,
): T {
  return result.status === 'fulfilled' ? result.value : fallback;
}
```

---

## Per-request Timeouts

Without a deadline, a slow upstream can hold the entire response. Wrap each
individual fetch in a race against an `AbortController` timeout:

```typescript
async function fetchWithTimeout<T>(
  url: string,
  options: RequestInit,
  timeoutMs: number,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status} from ${url}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

// Individual service fetchers
async function fetchPrice(productId: string, env: Env): Promise<PriceData> {
  return fetchWithTimeout<PriceData>(
    `${env.PRICING_SERVICE_URL}/products/${productId}/price`,
    { headers: { Authorization: `Bearer ${env.PRICING_TOKEN}` } },
    2_000, // 2 s deadline
  );
}

async function fetchInventory(productId: string, env: Env): Promise<InventoryData> {
  return fetchWithTimeout<InventoryData>(
    `${env.INVENTORY_SERVICE_URL}/stock/${productId}`,
    {},
    1_500,
  );
}

async function fetchReviews(productId: string, env: Env): Promise<ReviewsData> {
  return fetchWithTimeout<ReviewsData>(
    `${env.REVIEWS_SERVICE_URL}/products/${productId}/summary`,
    {},
    3_000,
  );
}

async function fetchShippingEstimate(productId: string, env: Env): Promise<ShippingData> {
  return fetchWithTimeout<ShippingData>(
    `${env.SHIPPING_SERVICE_URL}/estimate?productId=${productId}`,
    {},
    2_000,
  );
}
```

---

## Dynamic Scatter (Unknown N at Compile Time)

When the number of targets is determined at runtime (e.g. per-tenant service
roster):

```typescript
async function scatterGather<T>(
  targets: Array<{ key: string; url: string }>,
  buildRequest: (url: string) => RequestInit,
  timeoutMs: number,
): Promise<Record<string, T | null>> {
  const promises = targets.map(({ key, url }) =>
    fetchWithTimeout<T>(url, buildRequest(url), timeoutMs)
      .then((data) => ({ key, data }))
      .catch(() => ({ key, data: null as T | null }))
  );

  const results = await Promise.all(promises);

  return Object.fromEntries(results.map(({ key, data }) => [key, data]));
}

// Usage: pricing rollup across multiple suppliers
const supplierPrices = await scatterGather<SupplierPrice>(
  env.SUPPLIERS.map((s) => ({ key: s.id, url: s.priceUrl })),
  (url) => ({ headers: { 'X-Api-Key': env.SUPPLIER_API_KEY } }),
  1_500,
);
```

---

## Scatter to Service Bindings (Worker-to-Worker)

When downstream services are other Cloudflare Workers in the same account, use
**service bindings** instead of `fetch()` over the network. Service bindings
dispatch requests within Cloudflare's internal network, avoiding external
round-trip costs and TLS handshake overhead:

```typescript
// wrangler.toml
// [[services]]
// binding = "PRICING_SVC"
// service = "pricing-worker"
// [[services]]
// binding = "INVENTORY_SVC"
// service = "inventory-worker"

async function scatterToBindings(
  productId: string,
  env: Env,
): Promise<[PriceData | null, InventoryData | null]> {
  const [priceRes, inventoryRes] = await Promise.allSettled([
    env.PRICING_SVC.fetch(
      new Request(`https://internal/products/${productId}/price`)
    ).then((r) => r.json() as Promise<PriceData>),

    env.INVENTORY_SVC.fetch(
      new Request(`https://internal/stock/${productId}`)
    ).then((r) => r.json() as Promise<InventoryData>),
  ]);

  return [
    priceRes.status === 'fulfilled' ? priceRes.value : null,
    inventoryRes.status === 'fulfilled' ? inventoryRes.value : null,
  ];
}
```

Service binding calls still count toward the subrequest limit.

---

## Response Merging Strategies

| Strategy | When to use |
|---|---|
| Merge-with-defaults | Non-critical fields (reviews, recommendations) |
| Fail-fast (`Promise.all`) | Critical fields where partial data is useless |
| Waterfall fallback | Primary → secondary source if primary fails |
| Weighted merge | Combine multiple price sources into a lowest/average |

For product detail pages, **merge-with-defaults** is usually correct: show the
product even if reviews are down, but refuse to render if pricing is unavailable.

```typescript
const price = settled(priceResult, null);
if (price === null) {
  // Price is critical — return 503
  return new Response('Pricing service unavailable', { status: 503 });
}
```

---

## Anti-patterns

**Awaiting each fetch in sequence**
```typescript
// BAD: sequential — latency = Σ RTTi
const price = await fetchPrice(productId, env);
const inventory = await fetchInventory(productId, env);
```
Always start all promises before awaiting any.

**Using `Promise.all` when upstreams are unreliable**
`Promise.all` rejects as soon as any promise rejects. Use `Promise.allSettled`
when partial results are acceptable.

**Scattering without a timeout**
A hanging upstream blocks the entire gather phase. Always pair scatter calls with
`AbortController` timeouts set below the Worker's CPU time limit.

**Scattering to 100+ targets**
The Worker CPU time limit (50 ms on Free, 30 s on Paid as of mid-2026) and the
subrequest limit mean scatter operations should be bounded. For large N, batch
the scatter into rounds or use a queue fan-out pattern.

---

## Gotchas

- **CPU time vs wall-clock time**: `fetch()` does not consume CPU while awaiting
  the network. A Worker can await 50 `fetch()` calls in parallel without
  exceeding the 50 ms CPU limit, as long as JS processing between calls is
  minimal.

- **Subrequest limit is per-Worker invocation, not per-request**: Sub-Workers
  invoked via service bindings each have their own limit. Split extreme fan-outs
  into a two-level tree: one "coordinator" Worker fans out to N "leaf" Workers,
  each of which fans out to their own subset of targets.

- **`waitUntil` does not extend gather time**: `ctx.waitUntil()` extends the
  Worker's lifetime for background work *after* the response is sent. Do not use
  it to defer part of the scatter-gather; all gathering must complete before
  `Response` is returned.

- **D1 cannot be called in parallel within the same Worker invocation** (as of
  mid-2026): multiple concurrent D1 queries on the same binding may serialize
  internally. Mix D1 queries with external `fetch()` calls but do not expect
  parallel D1 speedup.

---

## Verification

```typescript
// Instrument with timing to confirm parallel execution
async function timedScatter(productId: string, env: Env) {
  const t0 = Date.now();
  const [p, i, r, s] = await Promise.allSettled([
    fetchPrice(productId, env),
    fetchInventory(productId, env),
    fetchReviews(productId, env),
    fetchShippingEstimate(productId, env),
  ]);
  const elapsed = Date.now() - t0;

  // elapsed should be ≈ max(individual RTTs), not their sum
  console.log({ elapsed, results: [p.status, i.status, r.status, s.status] });
}
```

In production, emit `elapsed` and individual per-service latencies as structured
log fields and alert if `elapsed` consistently exceeds `max(individual SLOs) + 50ms`.

---

## Related

- `fan-out-queues-workers.md` — async scatter without a response requirement.
- `bulkhead-pattern-workers-subrequests.md` — isolating subrequest failures so
  one upstream cannot starve others.
- `circuit-breaker-workers-d1-fetch.md` — wrapping each scatter leg in a circuit
  breaker to avoid hammering degraded upstreams.
- `request-coalescing-cache-stampede.md` — caching scatter results to avoid
  re-scattering on every request.

---

## Sources

- Enterprise Integration Patterns — Scatter-Gather:
  https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html
- Cloudflare Workers subrequest limits:
  https://developers.cloudflare.com/workers/platform/limits/#subrequests
- Cloudflare Workers service bindings:
  https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- MDN — Promise.allSettled():
  https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/allSettled
