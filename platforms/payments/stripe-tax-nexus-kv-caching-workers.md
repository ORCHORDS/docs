# Stripe Tax Nexus Calculation Caching with Workers KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Calling the Stripe Tax `/v1/tax/calculations` endpoint on every checkout page load adds 100–300 ms of latency and consumes API rate-limit budget unnecessarily. Tax applicability for a given (customer location, product tax code) pair changes only when Stripe updates its nexus rules or you change registrations — an event that happens at most a few times per month. The result is safe to cache aggressively in Workers KV.

## Context

Stripe Tax calculates whether tax applies and at what rate based on: merchant nexus registrations, customer ship-to address, and product tax code (PTC). None of these change per-request — they change on registration events (webhook `tax.settings.updated`, `tax.registration.created`). Caching the tax-applicable flag and estimated rate in KV with a TTL of 15 minutes eliminates redundant API calls while remaining correct within any reasonable registration change propagation window.

---

## KV Namespace (wrangler.toml)

```toml
[[kv_namespaces]]
binding = "TAX_CACHE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
preview_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

## Cache Key Design

```typescript
// src/lib/tax-cache-key.ts

/**
 * Cache key encodes the three factors that determine tax applicability.
 * country + region covers the customer nexus location.
 * ptc is Stripe's product tax code (e.g. "txcd_10000000" for SaaS).
 */
export function taxCacheKey(params: {
  country: string;       // ISO 3166-1 alpha-2
  region?: string;       // state/province code, e.g. "CA"
  ptc: string;           // product tax code
}): string {
  const region = params.region ?? "_";
  // Keep key short — KV keys max 512 bytes but KV list scans are slower with long keys
  return `tax:${params.country}:${region}:${params.ptc}`;
}
```

## Cached Stripe Tax Lookup

```typescript
// src/lib/stripe-tax.ts
import Stripe from "stripe";
import { taxCacheKey } from "./tax-cache-key";

const TAX_CACHE_TTL = 900; // 15 minutes

interface TaxEstimate {
  applicable: boolean;
  rate: number;          // 0–1, e.g. 0.0875 for 8.75 %
  currency: string;
  cachedAt: number;      // epoch ms
}

interface Env {
  STRIPE_SECRET_KEY: string;
  TAX_CACHE: KVNamespace;
}

export async function getOrFetchTaxEstimate(
  env: Env,
  params: {
    country: string;
    region?: string;
    ptc: string;
    amountCents: number;   // representative amount for rate calc
    currency: string;
  }
): Promise<TaxEstimate> {
  const cacheKey = taxCacheKey(params);

  // 1. Try KV cache first
  const cached = await env.TAX_CACHE.get<TaxEstimate>(cacheKey, "json");
  if (cached) return cached;

  // 2. Miss — call Stripe Tax
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: "2024-06-20" });

  const calc = await stripe.tax.calculations.create({
    currency: params.currency,
    line_items: [
      {
        amount: params.amountCents,
        reference: "item",
        tax_code: params.ptc,
      },
    ],
    customer_details: {
      address: {
        country: params.country,
        state: params.region,
      },
      address_source: "shipping",
    },
  });

  const item = calc.line_items.data[0];
  const taxAmount = item?.tax_amount ?? 0;
  const rate = taxAmount / params.amountCents;

  const result: TaxEstimate = {
    applicable: taxAmount > 0,
    rate,
    currency: params.currency,
    cachedAt: Date.now(),
  };

  // 3. Write to KV with TTL
  await env.TAX_CACHE.put(cacheKey, JSON.stringify(result), {
    expirationTtl: TAX_CACHE_TTL,
  });

  return result;
}
```

## Cache Invalidation on Registration Change

```typescript
// src/handlers/stripe-webhook.ts
// Invalidate KV entries when Stripe reports nexus changes

export async function handleTaxSettingsUpdated(
  env: Env,
  _event: Stripe.TaxSettingsUpdatedEvent
): Promise<void> {
  // List and delete all tax: keys
  // In production, use a tag-prefix strategy if you have millions of keys
  let cursor: string | undefined;
  do {
    const list = await env.TAX_CACHE.list({ prefix: "tax:", cursor });
    await Promise.all(list.keys.map((k) => env.TAX_CACHE.delete(k.name)));
    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);
}
```

## Applying Cached Rate to a Checkout

```typescript
// src/handlers/checkout.ts
import { getOrFetchTaxEstimate } from "../lib/stripe-tax";

export async function buildCheckoutResponse(
  env: Env,
  request: Request
): Promise<Response> {
  const body = await request.json<{
    country: string;
    region?: string;
    amountCents: number;
    currency: string;
    ptc: string;
  }>();

  const estimate = await getOrFetchTaxEstimate(env, body);

  const taxCents = estimate.applicable
    ? Math.round(body.amountCents * estimate.rate)
    : 0;

  return Response.json({
    subtotalCents: body.amountCents,
    taxCents,
    totalCents: body.amountCents + taxCents,
    taxRate: estimate.rate,
    taxApplicable: estimate.applicable,
    fromCache: Date.now() - estimate.cachedAt < 1000,
  });
}
```

## Warming the Cache at Deploy Time

```typescript
// src/scripts/warm-tax-cache.ts  (run via `wrangler dev` or a Cron Trigger)
// Pre-populate popular country/PTC combos so the first real user doesn't pay
// the latency penalty.

const POPULAR_COMBOS = [
  { country: "US", region: "CA", ptc: "txcd_10000000" },
  { country: "US", region: "NY", ptc: "txcd_10000000" },
  { country: "DE", ptc: "txcd_10000000" },
  { country: "GB", ptc: "txcd_10000000" },
];

export async function warmTaxCache(env: Env): Promise<void> {
  await Promise.all(
    POPULAR_COMBOS.map((combo) =>
      getOrFetchTaxEstimate(env, { ...combo, amountCents: 10000, currency: "usd" })
    )
  );
}
```

---

## Anti-patterns

- Caching the full `Stripe.Tax.Calculation` object — it includes a `calculation_id` tied to a specific amount that expires in 90 minutes; cache the *rate*, not the object.
- Using a TTL longer than 24 hours — Stripe can update nexus rules without a webhook (e.g. automatic economic-nexus threshold crossings).
- Treating a cache miss as a fatal error — the Stripe Tax API call is the fallback, not a secondary path.
- Keying only on country — US state-level rates vary dramatically; always include `region`.

## Gotchas

- KV's eventual consistency means a new Worker instance may serve a stale `get` for up to 60 s after a `put` or `delete` in another region. This is acceptable for tax rates but matters for cache invalidation timing.
- Stripe Tax requires a `currency` on the calculation; cache results per-currency if you support multi-currency (rates are currency-agnostic but the API call isn't).
- `tax.settings.updated` fires on *any* settings change (not just nexus), so blanket invalidation is safe.
- The `address_source` must match what you use at order time — mismatches (shipping vs. billing) produce different rates.

## Verification

```bash
# Hit the checkout endpoint twice — second call should return fromCache: true
wrangler dev --local
curl -X POST http://localhost:8787/checkout \
  -H "Content-Type: application/json" \
  -d '{"country":"US","region":"CA","amountCents":4999,"currency":"usd","ptc":"txcd_10000000"}'
# Check KV
wrangler kv key list --namespace-id=<id> --prefix=tax:
```

## Related

- `stripe-tax-calculation.md`
- `stripe-tax-customer-location-evidence.md`
- `stripe-tax-exemption-certificate-management-workers-d1.md`
- `stripe-tax-registration-effective-date-controls.md`
- `multi-currency-kv-exchange-rate-cache-edge-pricing.md`

## Sources

- https://docs.stripe.com/tax/custom
- https://docs.stripe.com/api/tax/calculations/create
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
