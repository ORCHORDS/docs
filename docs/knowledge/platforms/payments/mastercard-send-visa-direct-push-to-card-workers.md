# Mastercard Send / Visa Direct Push-to-Card Disbursements via Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You need to disburse funds directly to a debit card in near-real-time — gig-worker payouts, insurance claim settlements, marketplace seller withdrawals, or instant refunds — without the recipient providing bank account details. Mastercard Send (formerly MoneySend) and Visa Direct let you push money to any eligible Visa or Mastercard debit card within seconds. Integrating these networks through a payments gateway (Stripe, Adyen, or direct API) from a Cloudflare Worker requires careful handling of card eligibility checks, idempotency, and settlement timing.

---

## Context

Both networks work as **push-payment rails** layered on top of normal card infrastructure. The originating payment service provider (PSP) submits an Original Credit Transaction (OCT) on behalf of the platform. The card network routes it to the card-issuing bank, which credits the cardholder's account — typically within 30 minutes but sometimes instantly.

Key constraints relevant to Workers:
- **Eligibility pre-check required.** Not every debit card is OCT-enabled. PSPs expose an eligibility API that must be queried before submitting the disbursement.
- **Daily per-card limits.** Both networks impose per-card daily limits (typically $5,000–$10,000 USD). Platforms must track cumulative payouts in D1 to avoid declined transactions.
- **Idempotency is mandatory.** OCTs are money movement. A Worker crash between submit and confirmation must not result in duplicate disbursements.
- **Via Stripe Payouts / Adyen.** Most platforms access Visa Direct and Mastercard Send through a PSP rather than direct network membership. This article uses Stripe's Instant Payouts API as the integration layer; the pattern is equivalent for Adyen Transfer Instruments.

---

## Section 1 — Card Eligibility Check via Stripe Issuing / Payouts API

Before submitting a disbursement, verify the destination card supports instant payouts.

```typescript
// worker/src/lib/push-to-card.ts
import Stripe from "stripe";

export interface Env {
  STRIPE_SECRET_KEY: string;
  PAYOUTS_DB: D1Database;
  PAYOUT_IDEMPOTENCY_KV: KVNamespace;
}

/** Returns true if the payment method can receive Instant Payouts (Visa Direct / MC Send). */
export async function isCardEligibleForInstantPayout(
  paymentMethodId: string,
  env: Env
): Promise<boolean> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2024-11-20.acacia",
    httpClient: Stripe.createFetchHttpClient(),
  });

  const pm = await stripe.paymentMethods.retrieve(paymentMethodId);

  if (pm.type !== "card" || !pm.card) return false;

  // Stripe surfaces network-level capability via `available_payout_methods`
  // on the ExternalAccount object for Connect accounts. For PaymentMethods
  // attached to customers, check card brand + funding type as a proxy.
  const brand = pm.card.brand;          // "visa" | "mastercard" | ...
  const funding = pm.card.funding;      // "debit" | "credit" | "prepaid" | "unknown"

  if (funding !== "debit") return false;
  if (brand !== "visa" && brand !== "mastercard") return false;

  return true;
}
```

---

## Section 2 — D1 Schema for Payout Tracking and Daily Limits

```sql
-- migrations/0015_push_to_card_payouts.sql
CREATE TABLE IF NOT EXISTS push_to_card_payouts (
  id              TEXT PRIMARY KEY,    -- internal UUID
  stripe_payout_id TEXT UNIQUE,        -- po_... from Stripe
  recipient_id    TEXT NOT NULL,       -- your platform user ID
  payment_method_id TEXT NOT NULL,     -- pm_... or card fingerprint
  amount_cents    INTEGER NOT NULL,
  currency        TEXT NOT NULL DEFAULT 'usd',
  status          TEXT NOT NULL DEFAULT 'pending',
  -- pending | succeeded | failed | canceled
  failure_code    TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at      INTEGER NOT NULL,
  settled_at      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_ptcp_recipient_date
  ON push_to_card_payouts (recipient_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ptcp_fingerprint_date
  ON push_to_card_payouts (payment_method_id, created_at DESC);
```

```typescript
// worker/src/lib/push-to-card.ts (continued)
const DAILY_LIMIT_CENTS = 500_000; // $5,000 USD

export async function getDailyPayoutTotal(
  paymentMethodId: string,
  env: Env
): Promise<number> {
  const startOfDay = Math.floor(Date.now() / 1000) - (Date.now() / 1000 % 86400);

  const row = await env.PAYOUTS_DB.prepare(
    `SELECT COALESCE(SUM(amount_cents), 0) AS total
     FROM push_to_card_payouts
     WHERE payment_method_id = ?
       AND status IN ('pending', 'succeeded')
       AND created_at >= ?`
  )
    .bind(paymentMethodId, startOfDay)
    .first<{ total: number }>();

  return row?.total ?? 0;
}
```

---

## Section 3 — Submitting the Disbursement with Idempotency

```typescript
// worker/src/handlers/payout-handler.ts
import { v4 as uuidv4 } from "uuid";
import Stripe from "stripe";
import {
  isCardEligibleForInstantPayout,
  getDailyPayoutTotal,
  DAILY_LIMIT_CENTS,
  Env,
} from "../lib/push-to-card";

export async function disburseFunds(
  recipientId: string,
  paymentMethodId: string,
  amountCents: number,
  currency: string,
  env: Env
): Promise<{ success: boolean; payoutId?: string; error?: string }> {
  // 1. Eligibility gate
  const eligible = await isCardEligibleForInstantPayout(paymentMethodId, env);
  if (!eligible) {
    return { success: false, error: "card_not_eligible_for_instant_payout" };
  }

  // 2. Daily limit gate
  const dailyTotal = await getDailyPayoutTotal(paymentMethodId, env);
  if (dailyTotal + amountCents > DAILY_LIMIT_CENTS) {
    return { success: false, error: "daily_limit_exceeded" };
  }

  // 3. Idempotency key — deterministic per recipient + date + amount
  // to survive Worker restarts without double-paying
  const today = new Date().toISOString().split("T")[0];
  const idempotencyKey = `ptc:${recipientId}:${today}:${amountCents}:${paymentMethodId}`;

  // Check KV for a previously recorded outcome
  const cached = await env.PAYOUT_IDEMPOTENCY_KV.get(idempotencyKey);
  if (cached) {
    const parsed = JSON.parse(cached) as { payoutId: string; status: string };
    return { success: parsed.status === "succeeded", payoutId: parsed.payoutId };
  }

  const internalId = uuidv4();
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2024-11-20.acacia",
    httpClient: Stripe.createFetchHttpClient(),
  });

  // 4. Insert pending row before calling Stripe (fail-safe)
  await env.PAYOUTS_DB.prepare(
    `INSERT INTO push_to_card_payouts
       (id, recipient_id, payment_method_id, amount_cents, currency,
        status, idempotency_key, created_at)
     VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)`
  )
    .bind(internalId, recipientId, paymentMethodId, amountCents, currency,
          idempotencyKey, Math.floor(Date.now() / 1000))
    .run();

  // 5. Submit to Stripe Instant Payouts
  let stripePayout: Stripe.Payout;
  try {
    stripePayout = await stripe.payouts.create(
      {
        amount: amountCents,
        currency,
        method: "instant",
        destination: paymentMethodId,
        metadata: { recipient_id: recipientId, internal_id: internalId },
      },
      { idempotencyKey }
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    await env.PAYOUTS_DB.prepare(
      `UPDATE push_to_card_payouts
       SET status = 'failed', failure_code = ? WHERE id = ?`
    ).bind(msg, internalId).run();
    return { success: false, error: msg };
  }

  // 6. Update row and cache outcome
  const status = stripePayout.status === "paid" ? "succeeded" : stripePayout.status;
  await env.PAYOUTS_DB.prepare(
    `UPDATE push_to_card_payouts
     SET stripe_payout_id = ?, status = ?, settled_at = ?
     WHERE id = ?`
  )
    .bind(stripePayout.id, status, stripePayout.arrival_date, internalId)
    .run();

  await env.PAYOUT_IDEMPOTENCY_KV.put(
    idempotencyKey,
    JSON.stringify({ payoutId: stripePayout.id, status }),
    { expirationTtl: 86400 * 7 } // 7 days
  );

  return { success: true, payoutId: stripePayout.id };
}
```

---

## Section 4 — Webhook Handler for Payout Status Updates

```typescript
// worker/src/handlers/stripe-payout-webhook.ts
import Stripe from "stripe";
import { Env } from "../lib/push-to-card";

export async function handlePayoutWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get("stripe-signature") ?? "";

  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2024-11-20.acacia",
    httpClient: Stripe.createFetchHttpClient(),
  });

  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      body, sig, env.STRIPE_WEBHOOK_SECRET
    );
  } catch {
    return new Response("Invalid signature", { status: 400 });
  }

  if (event.type === "payout.paid" || event.type === "payout.failed") {
    const payout = event.data.object as Stripe.Payout;
    const status = event.type === "payout.paid" ? "succeeded" : "failed";

    await env.PAYOUTS_DB.prepare(
      `UPDATE push_to_card_payouts
       SET status = ?, failure_code = ?, settled_at = ?
       WHERE stripe_payout_id = ?`
    )
      .bind(
        status,
        (payout as Stripe.Payout & { failure_message?: string }).failure_message ?? null,
        payout.arrival_date,
        payout.id
      )
      .run();
  }

  return new Response(JSON.stringify({ received: true }), { status: 200 });
}
```

---

## Anti-Patterns

- **Checking eligibility once at onboarding and caching permanently.** Card OCT eligibility can change when a card is re-issued or the issuer disables the feature. Re-check per-disbursement or cache with a short TTL (≤ 24 hours).
- **Omitting the idempotency key on the Stripe API call.** Worker isolates can crash after the Stripe HTTP request is sent but before the response is stored. Without an idempotency key, a retry submits a second payout.
- **Relying solely on the API response for final status.** Instant payouts are asynchronous at the network level. `payout.status === "paid"` at create time means Stripe accepted it, not that the issuer credited the cardholder. Always consume `payout.paid` webhooks for authoritative settlement confirmation.
- **Ignoring daily limit tracking.** Each network imposes per-card daily limits. Exceeding them results in declined OCTs that waste retry budget and trigger issuer fraud flags.
- **Exposing raw payment method IDs in client responses.** Return only your internal payout ID to the client; never return `pm_` or `po_` identifiers that could be used to probe your Stripe account.

---

## Gotchas

1. **`method: "instant"` costs extra.** Stripe charges a fee (typically 0.5–1.5% with a minimum) for instant payouts vs. standard ACH. Build this into your platform's cost model.
2. **Arrival date vs. settlement time.** `payout.arrival_date` is the *estimated* credit date in Unix seconds (midnight UTC of the target day). Actual issuer credit can be minutes to hours earlier.
3. **Currency must match the Stripe account's default currency.** Cross-currency instant payouts require FX handling that most PSPs do not support on the OCT path.
4. **Mastercard Send and Visa Direct have separate network codes.** Stripe abstracts this; if you use a direct acquirer API you must specify the correct original credit indicator per scheme.
5. **KYC / AML applies to the *platform*, not the card.** Your platform is the money transmitter. Ensure your own sanctions screening (OFAC) runs before calling `disburseFunds`.

---

## Verification

```bash
# 1. Create a test payment method and verify eligibility response
stripe payment_methods create \
  --type card \
  --card[number]=4000056655665556 \
  --card[exp_month]=12 \
  --card[exp_year]=2027 \
  --card[cvc]=123
# 4000056655665556 is Stripe's test Visa debit number

# 2. Submit a test instant payout
stripe payouts create \
  --amount 1000 \
  --currency usd \
  --method instant

# 3. Verify the D1 row transitioned to succeeded after webhook delivery
wrangler d1 execute PAYOUTS_DB --remote \
  --command "SELECT id, stripe_payout_id, status, settled_at FROM push_to_card_payouts ORDER BY created_at DESC LIMIT 5;"

# 4. Confirm daily limit enforcement blocks a second over-limit payout
# (check that getDailyPayoutTotal returns >= DAILY_LIMIT_CENTS after first payout)
```

---

## Related

- `documentation/docs/policies/payments/payment-orchestration-multi-psp-routing.md`
- `documentation/docs/policies/payments/stripe-instant-payouts-scheduling.md`
- `documentation/docs/policies/payments/ofac-sanctions-screening-workers.md`
- `documentation/docs/policies/payments/idempotency-keys-payment-apis.md`
- `documentation/docs/policies/payments/payout-run-scheduling-engineering.md`

---

## Sources

- Stripe Instant Payouts — https://stripe.com/docs/payouts/instant-payouts
- Visa Direct for Issuers and Acquirers — https://developer.visa.com/capabilities/visa_direct
- Mastercard Send developer documentation — https://developer.mastercard.com/mastercard-send/documentation/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Stripe Payout webhooks — https://stripe.com/docs/api/events/types#event_types-payout.paid
