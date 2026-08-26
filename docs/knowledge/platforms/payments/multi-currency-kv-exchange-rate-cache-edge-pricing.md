# Multi-Currency Edge Pricing with Cloudflare KV Exchange Rate Cache

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Prices shown to international visitors are stale by hours or update with jarring jumps because exchange rates are fetched from a third-party API on every request. Origin latency for rate lookups also adds 200–400 ms to checkout page renders. You need fresh rates available at every Cloudflare edge location with sub-millisecond read latency and a controlled refresh cadence — without hitting Fixer.io or Open Exchange Rates (OXR) more than once per minute globally.

---

## Context

Cloudflare KV is eventually consistent and globally replicated, making it ideal for exchange-rate data: values are written once by a Worker cron, propagate to all ~300 edge locations in under 60 seconds, and are read with P99 < 1 ms from cache. The architecture is:

1. A scheduled Worker cron fetches rates from Fixer.io (or OXR) every N minutes.
2. It writes a single JSON blob to KV under a versioned key.
3. Every checkout Worker reads that KV key to convert prices at the edge.
4. Stripe receives the locally converted amount (or Stripe Adaptive Pricing handles it natively for supported currencies).

---

## 1. KV Namespace Setup and Wrangler Configuration

```toml
# wrangler.toml
name = "edge-pricing"
main = "src/worker.ts"
compatibility_date = "2025-01-01"

kv_namespaces = [
  { binding = "FX_RATES", id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", preview_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy" }
]

[triggers]
crons = ["*/5 * * * *"]   # refresh rates every 5 minutes
```

```typescript
// Type declaration for the KV binding
interface Env {
  FX_RATES: KVNamespace;
  FIXER_API_KEY: string;
  OXR_APP_ID: string;
}
```

---

## 2. Scheduled Rate Fetcher

```typescript
// src/cron/fetch-rates.ts
import type { Env } from "../types";

const BASE_CURRENCY = "USD";
const KV_KEY = "fx:rates:v1";
const KV_METADATA_KEY = "fx:meta:v1";

export interface RatePayload {
  base: string;
  timestamp: number; // Unix seconds
  rates: Record<string, number>; // e.g. { EUR: 0.92, GBP: 0.79, JPY: 149.5, ... }
  source: "fixer" | "oxr";
}

async function fetchFromFixer(apiKey: string): Promise<RatePayload> {
  const url = `https://data.fixer.io/api/latest?access_key=${apiKey}&base=${BASE_CURRENCY}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Fixer HTTP ${res.status}`);
  const data = (await res.json()) as {
    success: boolean;
    timestamp: number;
    base: string;
    rates: Record<string, number>;
  };
  if (!data.success) throw new Error("Fixer API returned success=false");
  return { base: data.base, timestamp: data.timestamp, rates: data.rates, source: "fixer" };
}

async function fetchFromOXR(appId: string): Promise<RatePayload> {
  const url = `https://openexchangerates.org/api/latest.json?app_id=${appId}&base=${BASE_CURRENCY}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`OXR HTTP ${res.status}`);
  const data = (await res.json()) as {
    timestamp: number;
    base: string;
    rates: Record<string, number>;
  };
  return { base: data.base, timestamp: data.timestamp, rates: data.rates, source: "oxr" };
}

export async function refreshRates(env: Env): Promise<RatePayload> {
  let payload: RatePayload;

  try {
    payload = await fetchFromFixer(env.FIXER_API_KEY);
  } catch (fixerErr) {
    console.warn("Fixer failed, falling back to OXR:", fixerErr);
    payload = await fetchFromOXR(env.OXR_APP_ID);
  }

  const json = JSON.stringify(payload);

  // Write with a 10-minute TTL as a safety net (cron writes every 5 min)
  await env.FX_RATES.put(KV_KEY, json, { expirationTtl: 600 });
  await env.FX_RATES.put(
    KV_METADATA_KEY,
    JSON.stringify({ fetchedAt: Date.now(), source: payload.source }),
    { expirationTtl: 600 }
  );

  console.log(`Rates refreshed from ${payload.source}: ${Object.keys(payload.rates).length} currencies`);
  return payload;
}
```

---

## 3. Edge Price Conversion

```typescript
// src/pricing/convert.ts
import type { RatePayload } from "../cron/fetch-rates";

const KV_KEY = "fx:rates:v1";

// Supported presentment currencies with their display rules
export const SUPPORTED_CURRENCIES: Record<
  string,
  { decimals: number; minorUnit: number; symbol: string }
> = {
  USD: { decimals: 2, minorUnit: 100, symbol: "$" },
  EUR: { decimals: 2, minorUnit: 100, symbol: "€" },
  GBP: { decimals: 2, minorUnit: 100, symbol: "£" },
  JPY: { decimals: 0, minorUnit: 1, symbol: "¥" },
  CAD: { decimals: 2, minorUnit: 100, symbol: "CA$" },
  AUD: { decimals: 2, minorUnit: 100, symbol: "A$" },
  BRL: { decimals: 2, minorUnit: 100, symbol: "R$" },
  INR: { decimals: 2, minorUnit: 100, symbol: "₹" },
};

export async function getRates(kv: KVNamespace): Promise<RatePayload | null> {
  const raw = await kv.get(KV_KEY);
  if (!raw) return null;
  return JSON.parse(raw) as RatePayload;
}

/**
 * Convert a USD amount (in cents) to the target currency's minor unit.
 * Returns null if currency is unsupported or rates are missing.
 */
export function convertFromUsdCents(
  usdCents: number,
  targetCurrency: string,
  rates: RatePayload
): number | null {
  const meta = SUPPORTED_CURRENCIES[targetCurrency.toUpperCase()];
  if (!meta) return null;
  if (targetCurrency.toUpperCase() === "USD") return usdCents;

  const rate = rates.rates[targetCurrency.toUpperCase()];
  if (!rate) return null;

  const usdAmount = usdCents / 100;
  const converted = usdAmount * rate;

  // Round to nearest minor unit using banker's rounding avoidance
  const raw = converted * meta.minorUnit;
  return Math.round(raw);
}

/**
 * Detect user currency from Accept-Language or CF-IPCountry header.
 * Falls back to USD.
 */
export function detectCurrency(request: Request): string {
  const country = request.headers.get("CF-IPCountry") ?? "US";
  const countryToCurrency: Record<string, string> = {
    US: "USD", GB: "GBP", DE: "EUR", FR: "EUR", JP: "JPY",
    CA: "CAD", AU: "AUD", BR: "BRL", IN: "INR", NL: "EUR",
    ES: "EUR", IT: "EUR", PT: "EUR", AT: "EUR", BE: "EUR",
    IE: "EUR", FI: "EUR", GR: "EUR",
  };
  return countryToCurrency[country] ?? "USD";
}
```

---

## 4. Generating Stripe Price Options at the Edge

Rather than creating a Stripe Price object per currency (which quickly becomes unmanageable), use `currency_options` on a single Stripe Price or calculate the presentment amount and pass `currency` + `amount` to a Payment Intent directly.

```typescript
// src/checkout/create-session.ts
import Stripe from "stripe";
import { getRates, convertFromUsdCents, detectCurrency, SUPPORTED_CURRENCIES } from "../pricing/convert";
import type { Env } from "../types";

const BASE_PRICE_USD_CENTS = 2900; // $29.00/month base price

export async function createCheckoutSession(
  request: Request,
  env: Env,
  stripeCustomerId: string
): Promise<string> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  const rates = await getRates(env.FX_RATES);

  const detectedCurrency = detectCurrency(request);
  let currency = detectedCurrency;
  let unitAmount = BASE_PRICE_USD_CENTS;

  if (rates) {
    const converted = convertFromUsdCents(BASE_PRICE_USD_CENTS, currency, rates);
    if (converted !== null) {
      unitAmount = converted;
    } else {
      // Unsupported currency — fall back to USD
      currency = "USD";
      unitAmount = BASE_PRICE_USD_CENTS;
    }
  } else {
    // KV miss (cold start or TTL expired) — fall back to USD
    currency = "USD";
    unitAmount = BASE_PRICE_USD_CENTS;
    console.warn("FX rates KV miss, falling back to USD");
  }

  const session = await stripe.checkout.sessions.create({
    customer: stripeCustomerId,
    payment_method_types: ["card"],
    line_items: [
      {
        price_data: {
          currency: currency.toLowerCase(),
          unit_amount: unitAmount,
          product_data: { name: "Pro Plan" },
          recurring: { interval: "month" },
        },
        quantity: 1,
      },
    ],
    mode: "subscription",
    success_url: `https://app.example.com/checkout/success?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `https://app.example.com/pricing`,
    metadata: {
      base_currency: "USD",
      base_amount_cents: String(BASE_PRICE_USD_CENTS),
      presentment_currency: currency,
      presentment_amount: String(unitAmount),
      fx_rate_timestamp: rates ? String(rates.timestamp) : "fallback",
    },
  });

  return session.url!;
}
```

---

## 5. Main Worker Entrypoint with Cron Handler

```typescript
// src/worker.ts
import { refreshRates } from "./cron/fetch-rates";
import { createCheckoutSession } from "./checkout/create-session";
import { getSession } from "./auth";
import type { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/checkout/start" && request.method === "POST") {
      const session = await getSession(request, env.JWT_SECRET);
      if (!session) return new Response(null, { status: 302, headers: { Location: "/login" } });

      const checkoutUrl = await createCheckoutSession(request, env, session.stripeCustomerId);
      return new Response(null, { status: 303, headers: { Location: checkoutUrl } });
    }

    // Expose current rates as a JSON endpoint (for client-side display)
    if (url.pathname === "/api/fx-rates" && request.method === "GET") {
      const raw = await env.FX_RATES.get("fx:rates:v1");
      if (!raw) return new Response("rates unavailable", { status: 503 });
      return new Response(raw, {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=60, stale-while-revalidate=120",
        },
      });
    }

    return new Response("Not Found", { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await refreshRates(env);
  },
};
```

---

## Anti-patterns

- **Fetching exchange rates on every checkout request.** Fixer.io free tier allows 100 requests/month; OXR free tier 1000/month. A single Worker cron is the only sustainable approach.
- **Storing rates per-currency as individual KV keys.** KV read latency is dominated by round-trips, not payload size. One key with all rates is 10× more efficient than 40 separate reads.
- **Using floating-point arithmetic for currency conversion.** Always convert to minor units (cents, pence, yen) using integer `Math.round()`. `0.1 + 0.2 !== 0.3` causes rounding errors that diverge over thousands of transactions.
- **Displaying the converted price to users without persisting the rate used.** Stripe will bill what you pass as `unit_amount`. Store `fx_rate_timestamp` in session metadata so you can reconcile disputes.
- **Silently failing to USD without telling the user.** Consider displaying a banner: "Prices shown in USD — your bank may charge a conversion fee."

---

## Gotchas

- **KV eventual consistency lag is up to 60 seconds.** In practice, edge nodes in the same region see writes in under 1 second, but globally expect up to 60 s. Set `expirationTtl` to 2× the cron interval as a safeguard against a missed cron run.
- **Fixer.io's free plan uses EUR as base, not USD.** You must cross-rate through EUR: `rate_USD_to_GBP = rates.GBP / rates.USD`. Fixer paid plans support arbitrary base currencies.
- **Zero-decimal currencies (JPY, KRW, VND).** `unit_amount` for JPY `1000` means ¥1000, not ¥10. The `SUPPORTED_CURRENCIES` map above handles this via `minorUnit: 1`.
- **Stripe does not accept all ISO 4217 currencies.** Validate against [Stripe's supported currencies list](https://docs.stripe.com/currencies) before passing `currency` to any Stripe API.
- **Price jumps at rate refresh boundaries can confuse returning visitors.** Cache the rate seen at session start in the checkout session metadata and honour that for the payment lifetime.
- **Workers cron granularity is 1 minute.** `*/5 * * * *` means at most 12 API calls/hour — well within Fixer free-tier limits at 100/month.

---

## Verification

```bash
# 1. Trigger cron manually via Wrangler
npx wrangler dev --local
# In a second terminal:
curl http://localhost:8787/__scheduled?cron=*/5+*+*+*+*

# 2. Inspect stored rates
npx wrangler kv:key get --namespace-id=<ID> "fx:rates:v1" | jq '.rates | {EUR, GBP, JPY, CAD}'

# 3. Check rate age
npx wrangler kv:key get --namespace-id=<ID> "fx:meta:v1" | jq '.fetchedAt | . / 1000 | todate'

# 4. Test checkout currency detection (simulate JP visitor)
curl -X POST https://your-worker.example.com/checkout/start \
  -H "Cookie: __sess=<test_jwt>" \
  -H "CF-IPCountry: JP"
# Expect: 303 redirect to Stripe Checkout with JPY pricing

# 5. Confirm metadata on Stripe session
stripe checkout sessions retrieve <cs_xxx> --api-key=sk_test_... \
  | jq '.metadata'
# Expect: presentment_currency=JPY, fx_rate_timestamp=<unix>
```

---

## Related

- `forex-rate-caching.md` — general forex caching patterns without Cloudflare-specific details
- `multi-currency-handling.md` — UI/UX patterns for currency display and selection
- `multi-currency-rounding-fees.md` — rounding rules and fee disclosure requirements
- `stripe-adaptive-pricing-presentment-reconciliation.md` — Stripe-native currency conversion as an alternative
- `payment-retry-exponential-backoff-cloudflare-queues.md` — queueing cron failures for retry

---

## Sources

- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Fixer.io API documentation: https://fixer.io/documentation
- Open Exchange Rates API: https://docs.openexchangerates.org/reference/api-introduction
- Stripe supported currencies: https://docs.stripe.com/currencies
- Stripe `price_data` with `currency`: https://docs.stripe.com/api/checkout/sessions/create#create_checkout_session-line_items-price_data
