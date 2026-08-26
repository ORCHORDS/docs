# Subscription Gifting with Stripe Gift Codes and D1 Redemption State Machine

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A user wants to buy a 3-month subscription gift for a friend. The buyer pays immediately; the recipient redeems a code later to activate a new or upgraded subscription for the gifted period, without entering payment details of their own. You need to handle purchase, code generation, email delivery, redemption, and Stripe subscription provisioning — with expiry enforcement and idempotent redemption.

This applies directly to Orchords / example project creator subscriptions where fans want to gift premium access to other users.

---

## Context

Stripe does not have a native "gift subscription" product. The canonical implementation:

1. **Buyer pays** via a standard Stripe Checkout Session (one-time `payment_intent`, not a subscription).
2. **On payment success** your Workers backend mints a cryptographically random gift code and stores it in D1 with metadata (plan, duration, buyer ID, expiry).
3. **Buyer or system emails the code** to the recipient.
4. **Recipient redeems** the code via a Workers API endpoint. The endpoint validates the code, creates or modifies a Stripe subscription with `trial_end` set to now + gifted duration, and marks the code used.

The gift period is modelled as a free trial — the recipient's subscription starts immediately but billing is deferred until the gift expires. If the recipient already has an active subscription, the gift extends their billing cycle via a `billing_cycle_anchor` shift or a coupon.

---

## Section 1 — D1 Schema for Gift Codes

```sql
-- migration: 0017_gift_codes.sql
CREATE TABLE IF NOT EXISTS gift_codes (
  id                  INTEGER  PRIMARY KEY AUTOINCREMENT,
  code                TEXT     NOT NULL UNIQUE,       -- 16-char base32 code
  buyer_user_id       TEXT     NOT NULL,
  recipient_email     TEXT,                           -- NULL until redemption if buyer did not specify
  plan_id             TEXT     NOT NULL,              -- e.g. 'pro_monthly'
  stripe_price_id     TEXT     NOT NULL,
  duration_days       INTEGER  NOT NULL,
  stripe_payment_id   TEXT     NOT NULL,              -- PaymentIntent or Checkout Session id
  status              TEXT     NOT NULL DEFAULT 'pending',
  -- pending (paid, awaiting email) | active (emailed) | redeemed | expired | voided
  redeemed_by_user_id TEXT,
  redeemed_at         INTEGER,
  expires_at          INTEGER  NOT NULL,              -- code validity window (e.g. 12 months)
  created_at          INTEGER  NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_gift_codes_code ON gift_codes(code);
CREATE INDEX IF NOT EXISTS idx_gift_codes_buyer ON gift_codes(buyer_user_id);
```

---

## Section 2 — Gift Purchase: Stripe Checkout Session

```typescript
// workers/src/handlers/gift-purchase.ts
import Stripe from 'stripe';
import { generateGiftCode } from '../lib/gift-code';

export interface GiftPurchaseRequest {
  buyerUserId: string;
  recipientEmail?: string;
  planId: string;
  stripePriceId: string;
  durationDays: number;
  successUrl: string;
  cancelUrl: string;
}

export async function createGiftCheckout(
  stripe: Stripe,
  env: Env,
  req: GiftPurchaseRequest,
): Promise<{ url: string }> {
  // Calculate one-time price for the gift period based on the monthly price
  // (simplified: duration_days / 30 * monthly_amount — in production use a fixed gift price)
  const session = await stripe.checkout.sessions.create({
    mode: 'payment',
    line_items: [
      {
        price: req.stripePriceId,   // a one-time "gift" price created in the Stripe Dashboard
        quantity: 1,
      },
    ],
    metadata: {
      type: 'gift_subscription',
      buyer_user_id: req.buyerUserId,
      recipient_email: req.recipientEmail ?? '',
      plan_id: req.planId,
      duration_days: String(req.durationDays),
    },
    customer_email: req.recipientEmail
      ? undefined
      : undefined,   // buyer pays from their own account
    success_url: req.successUrl + '?session_id={CHECKOUT_SESSION_ID}',
    cancel_url: req.cancelUrl,
    expires_at: Math.floor(Date.now() / 1000) + 1800,   // 30 min checkout window
  });

  return { url: session.url! };
}
```

---

## Section 3 — Gift Code Generation and Activation on Webhook

```typescript
// workers/src/lib/gift-code.ts
import { base32Encode } from './base32';    // tiny inline base32, no external lib

/**
 * Generates a 16-character base32 code from 10 random bytes.
 * Format: XXXX-XXXX-XXXX-XXXX  (groups of 4 for readability)
 */
export function generateGiftCode(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(10));
  const raw = base32Encode(bytes);              // 16 chars
  return `${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8, 12)}-${raw.slice(12, 16)}`;
}

// workers/src/webhooks/gift-checkout.ts
import Stripe from 'stripe';
import { generateGiftCode } from '../lib/gift-code';

export async function handleGiftCheckoutComplete(
  env: Env,
  session: Stripe.Checkout.Session,
): Promise<void> {
  if (session.metadata?.type !== 'gift_subscription') return;
  if (session.payment_status !== 'paid') return;

  const {
    buyer_user_id,
    recipient_email,
    plan_id,
    duration_days,
  } = session.metadata;

  const code = generateGiftCode();
  const expiresAt = Math.floor(Date.now() / 1000) + 365 * 86_400;  // 1 year to redeem

  await env.DB.prepare(
    `INSERT INTO gift_codes
       (code, buyer_user_id, recipient_email, plan_id, stripe_price_id,
        duration_days, stripe_payment_id, status, expires_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 'active', ?8)`,
  )
    .bind(
      code,
      buyer_user_id,
      recipient_email || null,
      plan_id,
      session.line_items?.data[0]?.price?.id ?? '',
      parseInt(duration_days, 10),
      session.payment_intent as string,
      expiresAt,
    )
    .run();

  // TODO: trigger email delivery (Workers Queue or KV-backed email job)
  await env.GIFT_EMAIL_QUEUE.send({
    to: recipient_email || buyer_user_id,   // fallback: send to buyer to forward
    code,
    plan_id,
    duration_days: parseInt(duration_days, 10),
    buyer_user_id,
  });
}
```

---

## Section 4 — Redemption Endpoint with Stripe Subscription Provisioning

```typescript
// workers/src/handlers/gift-redeem.ts
import Stripe from 'stripe';

export interface RedeemRequest {
  code: string;
  recipientUserId: string;
}

export async function redeemGiftCode(
  stripe: Stripe,
  env: Env,
  req: RedeemRequest,
): Promise<{ subscriptionId: string; accessUntil: string }> {
  const normalised = req.code.toUpperCase().replace(/[^A-Z2-7]/g, '');

  // 1. Validate and lock the gift code (compare-and-swap pattern)
  const gift = await env.DB.prepare(
    `SELECT * FROM gift_codes WHERE code = ?1 AND status = 'active'`,
  )
    .bind(req.code)
    .first<{
      id: number;
      stripe_price_id: string;
      duration_days: number;
      expires_at: number;
      plan_id: string;
    }>();

  if (!gift) {
    throw Object.assign(new Error('Gift code not found or already redeemed'), {
      code: 'INVALID_GIFT_CODE',
    });
  }

  if (gift.expires_at < Math.floor(Date.now() / 1000)) {
    throw Object.assign(new Error('Gift code has expired'), {
      code: 'GIFT_CODE_EXPIRED',
    });
  }

  // 2. Atomically mark as redeemed (prevents race conditions)
  const result = await env.DB.prepare(
    `UPDATE gift_codes
        SET status = 'redeemed',
            redeemed_by_user_id = ?1,
            redeemed_at = unixepoch()
      WHERE id = ?2 AND status = 'active'`,
  )
    .bind(req.recipientUserId, gift.id)
    .run();

  if (result.meta.changes === 0) {
    // Another request beat us to it
    throw Object.assign(new Error('Gift code already redeemed'), {
      code: 'GIFT_CODE_REDEEMED',
    });
  }

  // 3. Look up or create the recipient's Stripe customer
  const user = await env.DB.prepare(
    `SELECT stripe_customer_id, stripe_subscription_id FROM users WHERE id = ?1`,
  )
    .bind(req.recipientUserId)
    .first<{ stripe_customer_id: string | null; stripe_subscription_id: string | null }>();

  let customerId = user?.stripe_customer_id;
  if (!customerId) {
    const customer = await stripe.customers.create({
      metadata: { user_id: req.recipientUserId },
    });
    customerId = customer.id;
    await env.DB.prepare(
      `UPDATE users SET stripe_customer_id = ?1 WHERE id = ?2`,
    )
      .bind(customerId, req.recipientUserId)
      .run();
  }

  // 4. Create or extend subscription with trial period = gift duration
  const trialEnd = Math.floor(Date.now() / 1000) + gift.duration_days * 86_400;
  let sub: import('stripe').Stripe.Subscription;

  if (user?.stripe_subscription_id) {
    // Recipient already has a sub — extend the trial_end
    sub = await stripe.subscriptions.update(user.stripe_subscription_id, {
      trial_end: trialEnd,
      proration_behavior: 'none',
    });
  } else {
    // New subscription — no payment method required during trial
    sub = await stripe.subscriptions.create({
      customer: customerId,
      items: [{ price: gift.stripe_price_id }],
      trial_end: trialEnd,
      trial_settings: {
        end_behavior: { missing_payment_method: 'pause' },
      },
      metadata: { gifted: 'true', gift_code: req.code },
    });

    await env.DB.prepare(
      `UPDATE users SET stripe_subscription_id = ?1 WHERE id = ?2`,
    )
      .bind(sub.id, req.recipientUserId)
      .run();
  }

  return {
    subscriptionId: sub.id,
    accessUntil: new Date(trialEnd * 1000).toISOString(),
  };
}
```

---

## Section 5 — Gift Code Expiry Sweep (Scheduled Worker)

```typescript
// workers/src/cron/expire-gift-codes.ts
// Runs daily via Workers Cron Trigger

export async function expireGiftCodes(env: Env): Promise<void> {
  const result = await env.DB.prepare(
    `UPDATE gift_codes
        SET status = 'expired'
      WHERE status = 'active'
        AND expires_at < unixepoch()`,
  ).run();

  console.log(`Expired ${result.meta.changes} gift codes`);
}
```

`wrangler.toml` cron registration:

```toml
[triggers]
crons = ["0 3 * * *"]   # 03:00 UTC daily
```

---

## Anti-patterns

- **Using predictable codes (e.g. sequential integers or base64 of user IDs)**: codes must be unguessable. Use `crypto.getRandomValues` and encode as base32 or hex — never base64 of structured data.
- **Not atomically marking the code redeemed**: if two redemption requests arrive simultaneously for the same code (tab double-click, network retry), both will succeed without the compare-and-swap `WHERE status = 'active'` guard.
- **Setting `trial_end` in the past**: if the server clock drifts or the gift is 0 days, Stripe rejects the subscription creation. Validate `duration_days > 0` before calling the API.
- **Not handling `missing_payment_method` at trial end**: without `trial_settings.end_behavior.missing_payment_method = 'pause'`, Stripe cancels the subscription when the trial ends if no payment method is attached. Use `pause` to give the recipient a grace window to add a card.
- **Emailing the code synchronously in the Stripe webhook handler**: webhook handlers must return 200 quickly. Enqueue email delivery to a Workers Queue and return immediately.

---

## Gotchas

- **Partial gift + existing subscription**: `trial_end` on an update extends from the new date, not from the existing `trial_end`. If the recipient already has 15 days of gift remaining and redeems a 30-day gift, the new `trial_end` must be `max(current_trial_end, now) + duration_days`.
- **Coupon alternative**: Instead of `trial_end`, you can apply a 100%-off coupon for N months. This is cleaner for subscribers with established billing anchors but harder to explain to customers ("coupon" vs "gift period").
- **Tax on the gift purchase**: the buyer pays a one-time charge. Apply Stripe Tax or calculate sales tax on the one-time gift price, not on the resulting subscription (which has no immediate charge).
- **Gift to existing paying subscriber**: extending `trial_end` on an active (non-trial) subscription immediately pauses their billing cycle — their next invoice is pushed forward. This is usually desirable but confirm with product.
- **Refunding a gift before redemption**: void the gift code (set `status = 'voided'`) and issue a Stripe refund on the `payment_intent`. If already redeemed, you must also cancel or truncate the subscription.

---

## Verification

```bash
# 1. Create a gift checkout session
curl -X POST https://api.yourapp.com/gifts/purchase \
  -H "Authorization: Bearer $BUYER_JWT" \
  -d '{"planId":"pro_monthly","durationDays":90,"successUrl":"https://app.example.com/gift/success","cancelUrl":"https://app.example.com/gift"}'

# 2. Complete checkout in Stripe test mode and trigger webhook
stripe trigger checkout.session.completed \
  --override checkout.session:metadata.type=gift_subscription \
  --override checkout.session:metadata.buyer_user_id=$BUYER_ID \
  --override checkout.session:metadata.duration_days=90 \
  --override checkout.session:payment_status=paid

# 3. Confirm gift code created in D1
wrangler d1 execute DB --command \
  "SELECT code, status, expires_at FROM gift_codes WHERE buyer_user_id='$BUYER_ID' ORDER BY created_at DESC LIMIT 1;"

# 4. Redeem the code as recipient
curl -X POST https://api.yourapp.com/gifts/redeem \
  -H "Authorization: Bearer $RECIPIENT_JWT" \
  -d '{"code":"XXXX-XXXX-XXXX-XXXX"}'

# 5. Confirm subscription trial set
stripe subscriptions retrieve sub_xxx | jq '.trial_end'
# Expected: Unix timestamp ~90 days from now

# 6. Confirm code marked redeemed
wrangler d1 execute DB --command \
  "SELECT status, redeemed_by_user_id FROM gift_codes WHERE code='XXXX-XXXX-XXXX-XXXX';"
# Expected: redeemed | $RECIPIENT_USER_ID
```

---

## Related

- `stripe-trial-periods.md` — trial mechanics underpinning the gift period
- `stripe-coupon-discount.md` — coupon-based alternative to trial extension
- `stripe-cancellation-flow.md` — handling recipient cancellation mid-gift
- `credits-system-implementation.md` — credits alternative to gift subscriptions
- `payment-state-machine-design.md` — D1 state machine patterns
- `stripe-webhook-idempotency-workers.md` — idempotent webhook processing for gift activation

---

## Sources

- Stripe Docs — Subscription trials: https://stripe.com/docs/billing/subscriptions/trials
- Stripe API — Create subscription with trial_end: https://stripe.com/docs/api/subscriptions/create#create_subscription-trial_end
- Stripe Checkout Sessions: https://stripe.com/docs/api/checkout/sessions/create
- Cloudflare Workers Queues: https://developers.cloudflare.com/queues/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
