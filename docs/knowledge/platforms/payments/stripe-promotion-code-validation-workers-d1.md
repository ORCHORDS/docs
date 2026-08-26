# Stripe Promotion Code Validation with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You surface a promo code field at checkout and need to validate the code against Stripe before the customer submits payment. Validating client-side leaks your secret key; calling Stripe directly from the browser adds latency and exposes your entire coupon catalogue. You also need to track per-customer redemption caps, campaign budgets, and first-order-only restrictions that Stripe's built-in limits don't model precisely enough.

## Context

Stripe's `PromotionCode` object wraps a `Coupon` and adds `max_redemptions`, `expires_at`, `restrictions.first_time_transaction`, and `restrictions.minimum_amount`. However, you often need to enforce additional business rules: a code valid only for a specific product, a per-user redemption cap lower than the global cap, or an A/B test gate. A Cloudflare Worker acts as the validation proxy: it holds the Stripe secret key, checks Stripe's state, applies your extra rules from D1, and returns a sanitized result to the browser.

---

## 1. D1 Schema for Extended Promo Rules

```sql
-- migrations/0010_promo_rules.sql
CREATE TABLE IF NOT EXISTS promo_rules (
  promo_code_id   TEXT PRIMARY KEY,   -- Stripe PromotionCode id, e.g. promo_xxx
  allowed_skus    TEXT,               -- JSON array of price IDs, NULL = any
  per_user_cap    INTEGER DEFAULT 1,
  campaign_id     TEXT,
  active          INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS promo_redemptions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  promo_code_id   TEXT NOT NULL,
  customer_id     TEXT NOT NULL,      -- Stripe customer id or hashed email
  redeemed_at     INTEGER NOT NULL,   -- Unix epoch
  order_id        TEXT
);

CREATE INDEX IF NOT EXISTS idx_redemptions_lookup
  ON promo_redemptions (promo_code_id, customer_id);
```

## 2. Worker: Validation Endpoint

```typescript
// src/validate-promo.ts
import Stripe from 'stripe';

interface Env {
  STRIPE_SECRET_KEY: string;
  DB: D1Database;
}

interface ValidationRequest {
  code: string;
  customerId: string;   // Stripe customer id or anonymous fingerprint
  priceId?: string;     // product being purchased
  amountCents: number;
  currency: string;
}

export async function handleValidatePromo(
  req: Request,
  env: Env
): Promise<Response> {
  const body: ValidationRequest = await req.json();
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

  // 1. Resolve Stripe PromotionCode
  const list = await stripe.promotionCodes.list({
    code: body.code,
    active: true,
    limit: 1,
    expand: ['data.coupon'],
  });

  if (!list.data.length) {
    return jsonError('Invalid or expired promotion code.', 400);
  }

  const pc = list.data[0];
  const coupon = pc.coupon as Stripe.Coupon;

  // 2. Stripe-native checks
  if (pc.expires_at && pc.expires_at < Math.floor(Date.now() / 1000)) {
    return jsonError('This promotion code has expired.', 400);
  }
  if (pc.max_redemptions !== null && pc.times_redeemed >= pc.max_redemptions) {
    return jsonError('This promotion code has reached its redemption limit.', 400);
  }
  const minAmount = pc.restrictions?.minimum_amount ?? 0;
  if (body.amountCents < minAmount) {
    return jsonError(
      `Minimum order of ${minAmount / 100} ${body.currency.toUpperCase()} required.`,
      400
    );
  }

  // 3. D1 extended rules
  const rule = await env.DB.prepare(
    'SELECT * FROM promo_rules WHERE promo_code_id = ? AND active = 1'
  ).bind(pc.id).first<{
    allowed_skus: string | null;
    per_user_cap: number;
  }>();

  if (rule) {
    if (rule.allowed_skus && body.priceId) {
      const allowed: string[] = JSON.parse(rule.allowed_skus);
      if (!allowed.includes(body.priceId)) {
        return jsonError('This code is not valid for the selected product.', 400);
      }
    }

    const redemptionCount = await env.DB.prepare(
      `SELECT COUNT(*) AS cnt FROM promo_redemptions
       WHERE promo_code_id = ? AND customer_id = ?`
    ).bind(pc.id, body.customerId).first<{ cnt: number }>();

    if ((redemptionCount?.cnt ?? 0) >= rule.per_user_cap) {
      return jsonError('You have already used this promotion code.', 400);
    }
  }

  // 4. Return safe discount summary to browser
  const discount =
    coupon.amount_off !== null
      ? { type: 'fixed', amount: coupon.amount_off, currency: coupon.currency }
      : { type: 'percent', percent: coupon.percent_off };

  return Response.json({ valid: true, promotionCodeId: pc.id, discount });
}

function jsonError(message: string, status: number) {
  return Response.json({ valid: false, error: message }, { status });
}
```

## 3. Recording Redemptions After Payment Succeeds

```typescript
// Called from your stripe.checkout.session.completed webhook handler
export async function recordPromoRedemption(
  session: Stripe.Checkout.Session,
  env: Env
): Promise<void> {
  const discount = session.total_details?.breakdown?.discounts?.[0];
  if (!discount?.discount.promotion_code) return;

  const pcId =
    typeof discount.discount.promotion_code === 'string'
      ? discount.discount.promotion_code
      : discount.discount.promotion_code.id;

  await env.DB.prepare(
    `INSERT INTO promo_redemptions (promo_code_id, customer_id, redeemed_at, order_id)
     VALUES (?, ?, ?, ?)`
  ).bind(
    pcId,
    session.customer as string,
    Math.floor(Date.now() / 1000),
    session.id
  ).run();
}
```

## 4. Checkout Session: Applying the Validated Code

```typescript
// src/create-checkout.ts
export async function createCheckoutSession(
  stripe: Stripe,
  customerId: string,
  priceId: string,
  promotionCodeId: string | undefined
): Promise<string> {
  const params: Stripe.Checkout.SessionCreateParams = {
    customer: customerId,
    mode: 'payment',
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: 'https://example.com/success?session_id={CHECKOUT_SESSION_ID}',
    cancel_url: 'https://example.com/cart',
  };

  if (promotionCodeId) {
    // Pass the validated PromotionCode id directly — never the raw string
    params.discounts = [{ promotion_code: promotionCodeId }];
  }

  const session = await stripe.checkout.sessions.create(params);
  return session.url!;
}
```

## 5. Rate-Limiting the Validation Endpoint

```typescript
// Abuse prevention: a single IP hammering codes is a scraping attempt
import { RateLimiterWorker } from './rate-limiter'; // thin KV wrapper

export async function withRateLimit(
  req: Request,
  env: Env & { KV: KVNamespace },
  handler: (req: Request, env: Env & { KV: KVNamespace }) => Promise<Response>
): Promise<Response> {
  const ip = req.headers.get('CF-Connecting-IP') ?? 'unknown';
  const key = `promo_validate:${ip}`;
  const count = parseInt((await env.KV.get(key)) ?? '0', 10);

  if (count >= 10) {
    return Response.json({ valid: false, error: 'Too many requests.' }, { status: 429 });
  }

  await env.KV.put(key, String(count + 1), { expirationTtl: 60 });
  return handler(req, env);
}
```

---

## Anti-patterns

- **Validating promotion codes client-side** — exposes your coupon list and secret key; always proxy through a Worker.
- **Trusting the browser's discount result at checkout creation** — re-validate or pass the resolved `promotionCodeId` (not the raw string) so Stripe enforces its own server-side rules a second time.
- **Skipping the minimum-amount check** — Stripe's `restrictions.minimum_amount` is in the smallest currency unit for the coupon's currency, which may differ from the checkout currency.
- **Not recording redemptions in D1 before the webhook arrives** — between checkout completion and webhook delivery (up to 30 s), a fast user can redeem the same code twice. Record optimistically and reconcile on webhook.

## Gotchas

- `stripe.promotionCodes.list({ code })` matches case-insensitively, but returns the canonical casing. Always use the returned `pc.id`, not the user's input, when applying the code.
- A `Coupon` with `duration: 'repeating'` applied to a one-time Checkout session silently behaves as `once`.
- `pc.restrictions.first_time_transaction` is only enforced by Stripe when the customer object exists; anonymous checkouts bypass it. Enforce it yourself via D1 redemption history.
- Stripe's `times_redeemed` counter lags real-time by a few seconds under load. Your D1 per-user cap is the accurate control; Stripe's global cap is a backstop.

## Verification

```bash
# Validate a live promo code
curl -X POST https://your-worker.workers.dev/validate-promo \
  -H 'Content-Type: application/json' \
  -d '{"code":"SAVE20","customerId":"cus_xxx","amountCents":5000,"currency":"usd"}'

# Confirm redemption recorded
wrangler d1 execute YOUR_DB \
  --command "SELECT * FROM promo_redemptions WHERE promo_code_id = 'promo_xxx' LIMIT 5"

# Simulate exhausted per-user cap
# Call validate twice with same customerId — second call should return 400
```

## Related

- `stripe-coupon-discount.md`
- `stripe-checkout-session-cloudflare-workers.md`
- `payment-fraud-detection-velocity-checks.md`
- `stripe-webhook-idempotency-d1-event-log.md`
- `stripe-radar-value-list-governance.md`

## Sources

- https://docs.stripe.com/api/promotion_codes
- https://docs.stripe.com/billing/subscriptions/coupons
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
