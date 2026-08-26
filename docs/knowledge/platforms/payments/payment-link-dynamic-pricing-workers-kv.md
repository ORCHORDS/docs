# Payment Link Dynamic Pricing Workers KV

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You generate shareable payment links (via Stripe Payment Links, a hosted checkout,
or your own checkout pages) but need prices that vary per viewer: geo-based pricing,
coupon-adjusted rates, time-limited flash sales, B2B customer-specific quotes, or
demand-based surge pricing. Static payment links baked at creation time cannot
accommodate this. Cloudflare Workers intercepts each link visit, resolves the
current price from KV, and redirects to a personalized checkout.

## Context

The architecture has three layers:

1. **Price rules in KV**: Key-value pairs encode base prices, geo overrides, segment
   multipliers, active promotions, and expiry. Writes happen from your admin backend;
   reads happen at the Worker on every link visit.
2. **Worker as the routing layer**: A short URL like `pay.example.com/p/{linkId}`
   resolves via the Worker into a full Stripe Checkout Session with the resolved
   price embedded at session-creation time.
3. **Stripe Checkout Session created on demand**: Rather than reusing a static
   Payment Link, the Worker calls `POST /v1/checkout/sessions` with the computed
   price and a customer-specific success URL.

This avoids the Stripe Payment Links price limitation (static price IDs only) while
still using Stripe-hosted checkout for PCI compliance.

## KV Data Model

```typescript
// KV namespace: PRICING

// Base product price
// Key: `product:{productId}:base`
// Value: JSON
interface BasePrice {
  productId: string;
  name: string;
  amountCents: number;
  currency: string;
  stripePriceId?: string;   // optional fallback price id
}

// Geo override: per-country price
// Key: `product:{productId}:geo:{countryCode}`
// Value: JSON
interface GeoPriceOverride {
  amountCents: number;
  currency: string;
  reason?: string;           // e.g. "PPP adjustment"
}

// Active promotion
// Key: `promo:{code}`
// Value: JSON
interface PromoRule {
  code: string;
  type: 'fixed_off' | 'percent_off';
  value: number;             // cents or percent (0-100)
  applicableProducts: string[]; // empty = all
  expiresAt: number;         // unix ms
  maxUses?: number;
  usedCount: number;
}

// Segment override (e.g., enterprise tier)
// Key: `segment:{segmentId}:product:{productId}`
// Value: JSON
interface SegmentPrice {
  amountCents: number;
  currency: string;
}

// Link metadata (the what/who behind a payment link slug)
// Key: `link:{linkId}`
// Value: JSON
interface LinkConfig {
  productId: string;
  segmentId?: string;        // pre-assigned customer segment
  successUrl: string;
  cancelUrl: string;
  metadata?: Record<string, string>;
  expiresAt?: number;        // unix ms; absent = no expiry
}
```

## Price Resolution Worker

```typescript
// pricing-worker.ts
interface Env {
  PRICING: KVNamespace;
  STRIPE_SECRET_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // Route: /p/{linkId}[?promo=CODE]
    const match = url.pathname.match(/^\/p\/([^/?]+)/);
    if (!match) return new Response('Not found', { status: 404 });

    const linkId = match[1];
    const promoCode = url.searchParams.get('promo')?.toUpperCase() ?? null;
    const countryCode = request.headers.get('cf-ipcountry') ?? 'US';

    // 1. Load link config
    const linkJson = await env.PRICING.get(`link:${linkId}`);
    if (!linkJson) return new Response('Link not found', { status: 404 });

    const link: LinkConfig = JSON.parse(linkJson);
    if (link.expiresAt && Date.now() > link.expiresAt) {
      return new Response('Payment link has expired', { status: 410 });
    }

    // 2. Resolve price (parallel KV reads)
    const resolvedPrice = await resolvePrice(env, link, countryCode, promoCode);

    // 3. Create Stripe Checkout Session with computed price
    const session = await createCheckoutSession(env, link, resolvedPrice, promoCode);

    // 4. Redirect to Stripe-hosted checkout
    return Response.redirect(session.url, 303);
  },
};

interface ResolvedPrice {
  amountCents: number;
  currency: string;
  originalCents: number;
  discountCents: number;
  geoAdjusted: boolean;
  promoApplied: string | null;
}

async function resolvePrice(
  env: Env,
  link: LinkConfig,
  countryCode: string,
  promoCode: string | null
): Promise<ResolvedPrice> {
  const { productId, segmentId } = link;

  // Fetch base price, geo override, segment price, and promo in parallel
  const [baseJson, geoJson, segmentJson, promoJson] = await Promise.all([
    env.PRICING.get(`product:${productId}:base`),
    env.PRICING.get(`product:${productId}:geo:${countryCode}`),
    segmentId ? env.PRICING.get(`segment:${segmentId}:product:${productId}`) : Promise.resolve(null),
    promoCode ? env.PRICING.get(`promo:${promoCode}`) : Promise.resolve(null),
  ]);

  if (!baseJson) throw new Error(`No base price for product ${productId}`);

  const base: BasePrice = JSON.parse(baseJson);
  let amountCents = base.amountCents;
  let currency = base.currency;
  let geoAdjusted = false;

  // Priority: segment > geo > base
  if (segmentJson) {
    const seg: SegmentPrice = JSON.parse(segmentJson);
    amountCents = seg.amountCents;
    currency = seg.currency;
  } else if (geoJson) {
    const geo: GeoPriceOverride = JSON.parse(geoJson);
    amountCents = geo.amountCents;
    currency = geo.currency;
    geoAdjusted = true;
  }

  const originalCents = amountCents;
  let discountCents = 0;
  let promoApplied: string | null = null;

  // Apply promo if valid
  if (promoCode && promoJson) {
    const promo: PromoRule = JSON.parse(promoJson);
    const isExpired = Date.now() > promo.expiresAt;
    const isExhausted = promo.maxUses !== undefined && promo.usedCount >= promo.maxUses;
    const isApplicable =
      promo.applicableProducts.length === 0 || promo.applicableProducts.includes(productId);

    if (!isExpired && !isExhausted && isApplicable) {
      discountCents =
        promo.type === 'fixed_off'
          ? Math.min(promo.value, amountCents)
          : Math.round((amountCents * promo.value) / 100);
      amountCents -= discountCents;
      promoApplied = promoCode;
    }
  }

  // Floor at 50 cents (Stripe minimum)
  amountCents = Math.max(amountCents, 50);

  return { amountCents, currency, originalCents, discountCents, geoAdjusted, promoApplied };
}

async function createCheckoutSession(
  env: Env,
  link: LinkConfig,
  price: ResolvedPrice,
  promoCode: string | null
): Promise<{ url: string; id: string }> {
  const params = new URLSearchParams({
    mode: 'payment',
    'line_items[0][price_data][currency]': price.currency,
    'line_items[0][price_data][product_data][name]': link.productId,
    'line_items[0][price_data][unit_amount]': String(price.amountCents),
    'line_items[0][quantity]': '1',
    success_url: link.successUrl,
    cancel_url: link.cancelUrl,
    'metadata[link_id]': link.productId,
    'metadata[original_cents]': String(price.originalCents),
    'metadata[discount_cents]': String(price.discountCents),
    'metadata[geo_adjusted]': price.geoAdjusted ? '1' : '0',
    ...(promoCode ? { 'metadata[promo_code]': promoCode } : {}),
    ...flattenMetadata(link.metadata ?? {}),
  });

  const resp = await fetch('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params,
  });

  if (!resp.ok) {
    const err = await resp.json() as { error: { message: string } };
    throw new Error(`Stripe checkout session error: ${err.error.message}`);
  }

  return resp.json() as Promise<{ url: string; id: string }>;
}

function flattenMetadata(meta: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(meta).map(([k, v]) => [`metadata[${k}]`, v])
  );
}
```

## Admin API: Write Pricing Rules

```typescript
// admin-pricing.ts — called from your backend to update KV rules

async function setGeoPriceOverride(
  env: Env,
  productId: string,
  countryCode: string,
  amountCents: number,
  currency: string
): Promise<void> {
  const override: GeoPriceOverride = { amountCents, currency, reason: 'PPP' };
  await env.PRICING.put(
    `product:${productId}:geo:${countryCode}`,
    JSON.stringify(override)
  );
}

async function createPromo(env: Env, promo: Omit<PromoRule, 'usedCount'>): Promise<void> {
  const rule: PromoRule = { ...promo, usedCount: 0 };
  await env.PRICING.put(`promo:${promo.code}`, JSON.stringify(rule), {
    // KV TTL: expire the key 24h after the promo expires to auto-clean
    expiration: Math.ceil(promo.expiresAt / 1000) + 86400,
  });
}

async function createPaymentLink(
  env: Env,
  linkId: string,
  config: LinkConfig
): Promise<void> {
  await env.PRICING.put(`link:${linkId}`, JSON.stringify(config));
}

// Flash sale: set a geo or base price override with a short TTL
async function setFlashSalePrice(
  env: Env,
  productId: string,
  amountCents: number,
  durationSeconds: number
): Promise<void> {
  const base: BasePrice = {
    productId,
    name: productId,
    amountCents,
    currency: 'usd',
  };
  await env.PRICING.put(`product:${productId}:base`, JSON.stringify(base), {
    expirationTtl: durationSeconds,
  });
}
```

## Promo Use-Count Tracking

KV is eventually consistent and not suited for atomic counters. Use a lightweight
Durable Object or Stripe's built-in coupon `max_redemptions` to enforce hard use
limits. For soft limits with best-effort enforcement, update `usedCount` in KV
after each successful Stripe payment via webhook:

```typescript
// webhook-handler.ts (checkout.session.completed event)
async function handleCheckoutCompleted(env: Env, session: Record<string, unknown>): Promise<void> {
  const promoCode = (session['metadata'] as Record<string, string> | null)?.['promo_code'];
  if (!promoCode) return;

  const raw = await env.PRICING.get(`promo:${promoCode}`);
  if (!raw) return;

  const promo: PromoRule = JSON.parse(raw);
  promo.usedCount += 1;
  await env.PRICING.put(`promo:${promoCode}`, JSON.stringify(promo), {
    expiration: Math.ceil(promo.expiresAt / 1000) + 86400,
  });
}
```

## Anti-patterns

- **Creating Stripe Price objects on-the-fly per visit**: Each price object persists
  in your Stripe account. Use `price_data` in the session instead.
- **Caching resolved prices in the Worker**: The Worker should always read from KV
  so price changes take effect immediately. KV reads from the regional cache are
  already fast (~1ms for popular keys).
- **Putting all pricing logic in the Stripe metadata/coupon system**: Stripe coupons
  don't support geo-based logic or segment overrides. Keep complex rule evaluation
  in your Worker.
- **Exposing KV admin writes without auth**: Pricing KV mutations must require
  authenticated requests from your backend, not unauthenticated Worker routes.

## Gotchas

- KV is eventually consistent. Price updates may not be visible in all regions for
  up to 60 seconds after a write. Use `cacheTtl: 0` in reads during testing, and
  account for up to 60s propagation in production.
- Stripe Checkout Sessions expire in 24 hours. If you embed a session URL in an
  email campaign, redirect through your Worker each time rather than mailing the
  direct session URL.
- The `cf-ipcountry` header is `XX` for private/unknown IPs. Always fall back to
  base price when the country header is `XX` or absent.
- Currency mismatches between geo overrides can cause Stripe to reject the session
  (e.g., you cannot mix EUR prices with a USD-configured Stripe account without
  enabling multi-currency). Validate currency compatibility before writing geo rules.

## Verification

```bash
# Test geo-based pricing (simulate a German IP)
curl -H "cf-ipcountry: DE" https://pay.example.com/p/link_abc -L -I

# Inspect the KV rule for a product in Germany
wrangler kv:key get --binding=PRICING "product:prod_xyz:geo:DE"

# Verify promo code validity
wrangler kv:key get --binding=PRICING "promo:SUMMER25"

# Create a test link in KV
wrangler kv:key put --binding=PRICING "link:test123" \
  '{"productId":"prod_xyz","successUrl":"https://example.com/ty","cancelUrl":"https://example.com/cancel"}'
```

## Related

- `payment-link-generation.md` — Basic payment link creation
- `multi-currency-kv-exchange-rate-cache-edge-pricing.md` — FX rate caching for multi-currency
- `stripe-checkout-session-cloudflare-workers.md` — Checkout session creation
- `stripe-coupon-discount.md` — Stripe coupon and discount objects
- `forex-rate-caching.md` — Currency conversion rate caching

## Sources

- Stripe Checkout Sessions API: https://stripe.com/docs/api/checkout/sessions/create
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- Stripe price_data: https://stripe.com/docs/api/checkout/sessions/create#create_checkout_session-line_items-price_data
- Purchasing power parity pricing: https://stripe.com/docs/tax/adaptive-pricing
