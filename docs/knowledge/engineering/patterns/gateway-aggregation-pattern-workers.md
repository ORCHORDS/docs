# Gateway Aggregation Pattern — Workers Multiple APIs

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A mobile client needs to render a product page. It currently fires four separate requests: one for product details, one for inventory, one for pricing rules, and one for reviews. Each round-trip adds latency; on a slow mobile connection four serial fetches can take 1.5 s+. A gateway aggregation Worker fans the four calls out in parallel from the edge, merges the responses into a single JSON payload, and returns it in one round-trip — typically under 100 ms at the edge.

---

## Context

Cloudflare Workers sit at the edge, 50 ms or less from almost every user. Service bindings let them call downstream Workers with zero egress cost and near-zero latency. External APIs are called with `fetch()`. The pattern composes: the aggregation Worker is itself just another Worker that can be called via a service binding from a BFF or API gateway.

Gateway aggregation differs from the scatter-gather pattern in intent: scatter-gather fans identical work across homogeneous backends and merges partial results; gateway aggregation fans *different* requests to *heterogeneous* upstreams and merges the union of their schemas.

---

## Upstream Type Definitions

```typescript
// src/types.ts
export interface ProductDetails {
  id: string;
  name: string;
  description: string;
  imageUrl: string;
}

export interface Inventory {
  productId: string;
  available: number;
  warehouseId: string;
}

export interface Pricing {
  productId: string;
  priceCents: number;
  currency: string;
  discountPct: number;
}

export interface Review {
  id: string;
  rating: number;
  body: string;
  authorName: string;
}

export interface ProductPage {
  product: ProductDetails;
  inventory: Inventory | null;
  pricing: Pricing | null;
  reviews: Review[];
  aggregatedAt: string;
  errors: Record<string, string>;
}
```

---

## Parallel Fan-Out with `Promise.allSettled`

`Promise.allSettled` — not `Promise.all` — ensures a single upstream failure degrades gracefully rather than aborting the entire response.

```typescript
// src/aggregate.ts
import type { ProductDetails, Inventory, Pricing, Review, ProductPage } from './types';

interface Env {
  PRODUCT_SERVICE: Fetcher;  // service binding
  INVENTORY_URL: string;     // external API base
  PRICING_URL: string;
  REVIEWS_URL: string;
}

async function fetchJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, { ...init, cf: { cacheTtl: 30 } });
  if (!res.ok) throw new Error(`${res.status} ${res.url}`);
  return res.json<T>();
}

export async function aggregateProductPage(
  productId: string,
  env: Env,
): Promise<ProductPage> {
  const [detailsResult, inventoryResult, pricingResult, reviewsResult] =
    await Promise.allSettled([
      env.PRODUCT_SERVICE.fetch(`http://product-service/products/${productId}`)
        .then(r => r.json<ProductDetails>()),
      fetchJson<Inventory>(`${env.INVENTORY_URL}/inventory/${productId}`),
      fetchJson<Pricing>(`${env.PRICING_URL}/pricing/${productId}`),
      fetchJson<Review[]>(`${env.REVIEWS_URL}/reviews?productId=${productId}&limit=5`),
    ]);

  const errors: Record<string, string> = {};
  const extract = <T>(
    result: PromiseSettledResult<T>,
    key: string,
    fallback: T,
  ): T => {
    if (result.status === 'fulfilled') return result.value;
    errors[key] = result.reason instanceof Error ? result.reason.message : String(result.reason);
    return fallback;
  };

  return {
    product: extract(detailsResult, 'product', { id: productId, name: '', description: '', imageUrl: '' }),
    inventory: extract(inventoryResult, 'inventory', null),
    pricing: extract(pricingResult, 'pricing', null),
    reviews: extract(reviewsResult, 'reviews', []),
    aggregatedAt: new Date().toISOString(),
    errors,
  };
}
```

---

## Worker Handler with Cache-Control

```typescript
// src/index.ts
import { aggregateProductPage } from './aggregate';

interface Env {
  PRODUCT_SERVICE: Fetcher;
  INVENTORY_URL: string;
  PRICING_URL: string;
  REVIEWS_URL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/product-page\/([^/]+)$/);
    if (!match) return new Response('Not Found', { status: 404 });

    const productId = match[1];
    const page = await aggregateProductPage(productId, env);

    const hasErrors = Object.keys(page.errors).length > 0;
    return Response.json(page, {
      headers: {
        // Cache at edge for 15 s when fully successful; no-store on partial failures
        'Cache-Control': hasErrors ? 'no-store' : 'public, max-age=15, s-maxage=30',
        'X-Aggregation-Errors': hasErrors ? JSON.stringify(Object.keys(page.errors)) : '',
      },
    });
  },
};
```

---

## Timeout Budget per Upstream

Prevent a single slow upstream from holding the entire response beyond your SLO.

```typescript
function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms),
    ),
  ]);
}

// In aggregateProductPage, wrap each call:
fetchJson<Inventory>(`${env.INVENTORY_URL}/inventory/${productId}`)
  |> withTimeout(%, 800, 'inventory')
```

Or using standard chaining:

```typescript
withTimeout(
  fetchJson<Inventory>(`${env.INVENTORY_URL}/inventory/${productId}`),
  800,
  'inventory',
),
```

---

## Response Schema Versioning

Clients should know which version of the aggregated schema they received so they can degrade gracefully when new fields arrive.

```typescript
const SCHEMA_VERSION = '2026-08-01';

return Response.json(
  { schemaVersion: SCHEMA_VERSION, ...page },
  { headers: { 'X-Schema-Version': SCHEMA_VERSION } },
);
```

---

## Anti-patterns

- **Using `Promise.all` instead of `Promise.allSettled`**: a single 500 from the reviews service aborts the entire response, giving the client *nothing* instead of a product page without reviews.
- **Fetching upstreams sequentially**: removing the `await` from fan-out and using `Promise.allSettled` cuts wall-clock time from the sum of latencies to the max.
- **Returning raw upstream error bodies to clients**: upstream error messages may contain internal hostnames, stack traces, or sensitive details. Normalise to `{ error: 'upstream_failed' }`.
- **Caching aggregated responses with long TTLs**: inventory and pricing change frequently. Cache at the upstream level (short `cf.cacheTtl`) rather than caching the aggregated payload for minutes.
- **Bloating the aggregated payload with full upstream responses**: select and project only the fields the client actually needs; large reviews payloads kill mobile performance.

---

## Gotchas

- Workers have a **50 simultaneous subrequest** limit. Fan-out to more than 50 upstreams per request requires batching or a recursive aggregation tree.
- Service binding calls (`env.PRODUCT_SERVICE.fetch(...)`) do not count against egress but **do** count against the 50 subrequest limit.
- `fetch()` in Workers does not support `AbortController` + `AbortSignal` in the same way Node.js does; use `Promise.race` with a `setTimeout` promise for timeouts.
- The aggregation Worker's CPU time is the sum of JSON deserialisation across all upstreams. For very large payloads consider streaming with `TransformStream`.
- `cf: { cacheTtl: 30 }` in `fetch()` caches at Cloudflare's network layer, not in the Worker's memory — the cache key is the URL, so parameterise it correctly.

---

## Verification

```bash
# Start dev with multiple service bindings
npx wrangler dev --config wrangler.toml

# Single request replaces four
curl -s http://localhost:8787/product-page/prod_123 | jq '.errors'
# {} — all upstreams healthy

# Simulate inventory failure
# (take inventory mock offline, re-curl)
curl -s http://localhost:8787/product-page/prod_123 | jq '.errors'
# {"inventory":"503 http://..."}

# Verify timing — should be ~max(upstream latencies), not sum
time curl -s http://localhost:8787/product-page/prod_123 > /dev/null
```

---

## Related

- `scatter-gather-parallel-workers.md`
- `backend-for-frontend-bff-pattern.md`
- `api-gateway-pattern.md`
- `parallel-pipeline-workers-promise-all.md`
- `timeout-cascade-prevention-workers-fetch.md`
- `circuit-breaker-workers-d1-fetch.md`

---

## Sources

- Cloudflare Workers docs — Subrequests, Service Bindings (2026)
- Microsoft Azure Architecture Center — "Gateway Aggregation pattern" (2024)
- Release It!, Nygard — "Timeouts" and "Fail Fast"
- MDN — `Promise.allSettled()` (2026)
