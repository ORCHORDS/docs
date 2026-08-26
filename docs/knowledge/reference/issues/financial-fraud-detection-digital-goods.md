# Financial Fraud Detection for Digital Goods

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A platform selling digital goods (in-game items, NFT drops, subscription upgrades, virtual currency packs, digital gift cards) observes a pattern: a cluster of newly created accounts purchases high-value items with stolen credit cards, immediately transfers the goods to a receiver account, and the receiver liquidates them on secondary markets. Chargebacks arrive 30–90 days later. By then, the goods are gone, the accounts are banned, and the platform eats both the merchandise loss and the chargeback fee (typically $15–$50 per dispute plus an elevated dispute ratio penalty from Stripe or Adyen if the rate exceeds 0.75 %).

Secondary patterns: gift card fraud (purchase + instant full redemption in a different region), account-farming (bulk accounts buying discounted bundle packs for resale), and trial-abuse fraud (spin up free trials across email aliases and never convert, harvesting trial benefits).

## Context

Digital goods are uniquely attractive to fraudsters: instant delivery, no physical shipping address required, immediate liquidity through gray markets, and no return/recovery mechanism once delivered. Unlike physical fraud, reversals are pure loss — the seller cannot reclaim delivered digital content.

The detection stack runs entirely on Cloudflare Workers + D1 + KV + Queues. Stripe Radar handles card-level signals. A custom fraud scoring layer sits between the checkout intent API and the Stripe PaymentIntent creation, deciding whether to add a 3DS challenge, delay fulfillment, or reject the transaction outright. Decisions must complete within 200 ms to stay inside checkout UX tolerances.

Regulatory angle: PCI DSS v4.0 Requirement 10 (audit logs) and Requirement 6.4.3 (payment page scripts) apply. FATF guidelines on virtual asset fraud affect platforms operating in regulated jurisdictions. EU PSD2 Strong Customer Authentication (SCA) mandates 3DS for card payments over €30 unless the platform qualifies for a TRA (Transaction Risk Analysis) exemption — which requires demonstrating a fraud rate below 0.13 %.

## Pre-Purchase Risk Scoring

A Worker intercepts the checkout intent before any PaymentIntent is created. It assembles account-level and session-level signals into a fraud score.

```typescript
// workers/fraud-scorer.ts
export interface PurchaseContext {
  accountId: string;
  sessionId: string;
  ip: string;
  country: string;            // from CF header
  billingCountry: string;     // from submitted card billing address
  itemId: string;
  itemValueCents: number;
  isDigitalInstantDelivery: boolean;
  accountAgeDays: number;     // days since account creation
  accountVerifiedEmail: boolean;
  priorChargebacks: number;   // lifetime chargeback count on this account
  priorSuccessfulPurchases: number;
}

export interface FraudDecision {
  score: number;              // 0–100
  action: "allow" | "require_3ds" | "delay_24h" | "reject";
  reasons: string[];
}

export async function scorePurchase(
  ctx: PurchaseContext,
  env: Env
): Promise<FraudDecision> {
  const reasons: string[] = [];
  let score = 0;

  // --- Account-level signals ---
  if (ctx.accountAgeDays < 1) { score += 35; reasons.push("account_age_under_1d"); }
  else if (ctx.accountAgeDays < 7) { score += 15; reasons.push("account_age_under_7d"); }

  if (!ctx.accountVerifiedEmail) { score += 20; reasons.push("unverified_email"); }
  if (ctx.priorChargebacks > 0) { score += 40; reasons.push("prior_chargeback"); }
  if (ctx.priorSuccessfulPurchases === 0) { score += 10; reasons.push("first_purchase"); }

  // --- Geographic mismatch ---
  if (ctx.country !== ctx.billingCountry) {
    score += 20;
    reasons.push(`geo_mismatch:${ctx.country}!=${ctx.billingCountry}`);
  }

  // --- Velocity: purchases from same IP in last hour ---
  const ipVelKey = `fraud:ip_vel:${ctx.ip}`;
  const ipVel = Number(await env.KV.get(ipVelKey) ?? "0");
  if (ipVel >= 5) { score += 30; reasons.push("ip_velocity_high"); }
  else if (ipVel >= 2) { score += 10; reasons.push("ip_velocity_elevated"); }

  // --- High-value instant delivery on new account ---
  if (ctx.isDigitalInstantDelivery && ctx.itemValueCents > 4999 && ctx.accountAgeDays < 7) {
    score += 20;
    reasons.push("high_value_instant_new_account");
  }

  // --- Receiving-account pattern: was this item previously transferred TO this account? ---
  const receiverFlagKey = `fraud:receiver:${ctx.accountId}`;
  const isKnownReceiver = await env.KV.get(receiverFlagKey);
  if (isKnownReceiver) { score += 35; reasons.push("known_receiver_account"); }

  score = Math.min(score, 100);

  let action: FraudDecision["action"];
  if (score >= 75) action = "reject";
  else if (score >= 55) action = "delay_24h";
  else if (score >= 30) action = "require_3ds";
  else action = "allow";

  // Persist decision to D1 for chargeback correlation later
  await env.DB.prepare(
    `INSERT INTO fraud_decisions
       (account_id, item_id, value_cents, score, action, reasons, ts)
     VALUES (?,?,?,?,?,?,?)`
  ).bind(
    ctx.accountId, ctx.itemId, ctx.itemValueCents,
    score, action, JSON.stringify(reasons), Date.now()
  ).run();

  // Increment IP velocity counter
  await env.KV.put(ipVelKey, String(ipVel + 1), { expirationTtl: 3600 });

  return { score, action, reasons };
}
```

## Fulfillment Gate and Delay Queue

For `delay_24h` decisions, deliver the digital good to a pending escrow state rather than the account's active inventory. A Cloudflare Queue consumer releases or cancels after the review window.

```typescript
// workers/fulfillment-gate.ts
import type { FraudDecision } from "./fraud-scorer";

export async function gateFulfillment(
  purchaseId: string,
  decision: FraudDecision,
  env: Env
): Promise<{ status: "fulfilled" | "held" | "rejected"; heldUntil?: number }> {
  if (decision.action === "reject") {
    await env.DB.prepare(
      "UPDATE purchases SET status = 'rejected', updated_at = ? WHERE id = ?"
    ).bind(Date.now(), purchaseId).run();
    return { status: "rejected" };
  }

  if (decision.action === "delay_24h") {
    const heldUntil = Date.now() + 24 * 3600 * 1000;
    await env.DB.prepare(
      "UPDATE purchases SET status = 'held', held_until = ?, updated_at = ? WHERE id = ?"
    ).bind(heldUntil, Date.now(), purchaseId).run();

    // Enqueue a review job — consumer will auto-release if no chargeback signal arrives
    await env.FRAUD_QUEUE.send(
      { type: "held_purchase_review", purchaseId, heldUntil },
      { delaySeconds: 86400 }
    );
    return { status: "held", heldUntil };
  }

  // allow or require_3ds (3DS was already completed upstream) — immediate fulfillment
  await env.DB.prepare(
    "UPDATE purchases SET status = 'fulfilled', fulfilled_at = ?, updated_at = ? WHERE id = ?"
  ).bind(Date.now(), Date.now(), purchaseId).run();
  return { status: "fulfilled" };
}

// Queue consumer — called by Cloudflare Queues after delay
export async function handleFraudQueueMessage(
  message: { type: string; purchaseId: string; heldUntil: number },
  env: Env
): Promise<void> {
  if (message.type !== "held_purchase_review") return;

  // Check if any chargeback or manual flag arrived during hold
  const flagged = await env.DB.prepare(
    "SELECT 1 FROM fraud_flags WHERE purchase_id = ? LIMIT 1"
  ).bind(message.purchaseId).first();

  if (flagged) {
    await env.DB.prepare(
      "UPDATE purchases SET status = 'rejected_post_hold', updated_at = ? WHERE id = ?"
    ).bind(Date.now(), message.purchaseId).run();
  } else {
    await env.DB.prepare(
      "UPDATE purchases SET status = 'fulfilled', fulfilled_at = ?, updated_at = ? WHERE id = ?"
    ).bind(Date.now(), Date.now(), message.purchaseId).run();
    await deliverDigitalGood(message.purchaseId, env);
  }
}

declare function deliverDigitalGood(purchaseId: string, env: Env): Promise<void>;
```

## Chargeback Signal Loop and Receiver Flagging

When Stripe sends a `charge.dispute.created` webhook, correlate it back to the purchase and flag any downstream accounts that received transferred goods.

```typescript
// workers/chargeback-handler.ts
export async function handleStripeDisputeWebhook(
  event: { data: { object: { payment_intent: string; amount: number } } },
  env: Env
): Promise<void> {
  const paymentIntentId = event.data.object.payment_intent;

  // Find the purchase
  const purchase = await env.DB.prepare(
    "SELECT id, account_id, item_id FROM purchases WHERE stripe_payment_intent_id = ?"
  ).bind(paymentIntentId).first<{ id: string; account_id: string; item_id: string }>();
  if (!purchase) return;

  // Log chargeback
  await env.DB.prepare(
    "INSERT INTO fraud_flags (purchase_id, account_id, flag_type, ts) VALUES (?,?,?,?)"
  ).bind(purchase.id, purchase.account_id, "chargeback", Date.now()).run();

  // Increment account lifetime chargeback count
  await env.DB.prepare(
    "UPDATE accounts SET chargeback_count = chargeback_count + 1 WHERE id = ?"
  ).bind(purchase.account_id).run();

  // Find all accounts that received transferred goods from this purchase
  const receivers = await env.DB.prepare(
    `SELECT DISTINCT to_account_id FROM item_transfers
     WHERE item_id = ? AND from_account_id = ? AND created_at > ?`
  ).bind(
    purchase.item_id,
    purchase.account_id,
    Date.now() - 90 * 24 * 3600 * 1000
  ).all<{ to_account_id: string }>();

  // Flag receiver accounts for elevated fraud scoring
  for (const row of receivers.results) {
    await env.KV.put(
      `fraud:receiver:${row.to_account_id}`,
      JSON.stringify({ source_purchase: purchase.id, flagged_at: Date.now() }),
      { expirationTtl: 90 * 24 * 3600 }
    );
  }
}
```

## Stripe Radar Rule Integration

Custom Stripe Radar rules reinforce the Worker-level scoring. Set these in the Stripe Dashboard under Radar Rules.

```
# Block when metadata fraud_score flag is set by the Worker
block if :metadata_fraud_decision: = 'reject'

# Require 3DS when Worker scored 30+
request_three_d_secure if :metadata_fraud_decision: = 'require_3ds'

# Block new cards on accounts with prior chargebacks
block if :customer_chargeback_count: > 0 and :customer_account_age_days: < 90

# Block transactions where billing country != IP country and item is instant-digital
block if :card_country: != :ip_country: and :metadata_is_instant_digital: = 'true' and :amount_in_cents: > 4999
```

Pass metadata when creating the PaymentIntent from the Worker:

```typescript
const paymentIntent = await stripe.paymentIntents.create({
  amount: ctx.itemValueCents,
  currency: "usd",
  metadata: {
    fraud_score: String(decision.score),
    fraud_decision: decision.action,
    is_instant_digital: String(ctx.isDigitalInstantDelivery),
    account_age_days: String(ctx.accountAgeDays),
  },
});
```

## Anti-patterns

- **Blocking all new accounts from purchasing high-value items** — conversion rate tanks; the correct lever is delay + 3DS, not outright rejection for first purchases.
- **Relying solely on Stripe Radar without a pre-creation scoring layer** — by the time Stripe evaluates the charge, a PaymentIntent has been created and the card auth has already touched the issuer network; false-positive blocks after auth initiation create user experience problems.
- **Not persisting fraud decisions to D1** — without a log, you cannot retrospectively correlate chargebacks to scoring factors and calibrate thresholds.
- **Flagging receiver accounts permanently** — a legitimate buyer who unknowingly purchased a fraudulently-sourced item should be cleared after a review period; use KV TTLs, not permanent D1 flags.
- **Delaying all purchases by 24 hours as a blanket policy** — this destroys the instant-delivery value proposition and will suppress conversion on legitimate high-value purchases.
- **Passing fraud metadata in URL query params** — metadata must travel in the signed PaymentIntent body, not the URL, to prevent tampering.

## Gotchas

- Stripe dispute webhooks arrive 1–90 days after the payment. Storing `stripe_payment_intent_id` on the purchase row at creation time is required to correlate disputes back to items.
- `env.FRAUD_QUEUE.send()` with `delaySeconds` is only supported on Cloudflare Queues — verify the binding type is `Queue` in `wrangler.toml`, not `KVNamespace`.
- D1's `all()` returns `{ results: [] }` (not null) when there are no rows; iterate `results`, not the wrapper.
- The IP velocity counter in KV must use `expirationTtl` (seconds), not `expiration` (Unix timestamp). Confusing them yields keys that expire in the Unix epoch past.
- Stripe's `charge.dispute.created` event fires after the card issuer opens the dispute, not when the chargeback is filed with you. There is a 30–75 day lag from purchase to this event — your 24 h hold only catches immediate card-testing fraud.
- Gift card fraud moves fast: a fraudster can purchase and fully redeem a $200 gift card in under 60 seconds. Require email verification before any gift card issuance, and rate-limit redemptions per new-account to one per 24 h.

## Verification

```bash
# 1. Simulate high-risk checkout (new account, geo mismatch, high value)
curl -X POST https://api.example.com/checkout/intent \
  -H "Authorization: Bearer <new_account_token>" \
  -H "CF-IPCountry: NG" \
  -d '{"item_id":"premium_pack","billing_country":"US"}'
# Expect: action = "reject" or "delay_24h"

# 2. Check D1 for recorded fraud decision
wrangler d1 execute DB --command \
  "SELECT * FROM fraud_decisions WHERE account_id='...' ORDER BY ts DESC LIMIT 5"

# 3. Verify held purchases in queue
wrangler d1 execute DB --command \
  "SELECT id, status, held_until FROM purchases WHERE status='held' LIMIT 10"

# 4. Simulate Stripe dispute webhook
curl -X POST https://api.example.com/webhooks/stripe \
  -H "Stripe-Signature: <computed_sig>" \
  -d '{"type":"charge.dispute.created","data":{"object":{"payment_intent":"pi_test"}}}'

# 5. Confirm receiver account KV flag set
wrangler kv key get --binding=KV "fraud:receiver:<receiverAccountId>"
```

## Related

- `account-takeover-detection-prevention.md` — ATO is the entry vector for fraudulent purchases
- `botnet-registration-detection-turnstile-fingerprinting.md` — bulk account farming at registration
- `platform-trust-score-cloudflare-signals.md` — composite trust scoring
- `repeat-offender-detection-anonymous-sessions.md` — ban evasion after fraud flag
- `cryptocurrency-regulatory-risk-platform.md` — virtual currency compliance

## Sources

- Stripe Radar documentation — `stripe.com/docs/radar`
- Stripe Dispute Handling Guide — `stripe.com/docs/disputes`
- FATF Guidance on Virtual Assets — 2023 update
- PCI DSS v4.0 Requirements 6 and 10
- EU PSD2 RTS on Strong Customer Authentication, Article 18 (TRA exemption thresholds)
- Cloudflare Queues documentation — `developers.cloudflare.com/queues`
