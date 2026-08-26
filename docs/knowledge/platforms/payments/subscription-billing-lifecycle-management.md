# Subscription Billing Lifecycle Management

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Subscriptions silently lapse without payment, creators lose
revenue because dunning emails are not sent, or users are
incorrectly locked out (or granted access) during the grace
period after a failed renewal.

## Context

example.com sells monthly and annual subscriptions to fan
content. Billing is handled by Stripe Subscriptions. Our
Cloudflare Worker handles Stripe webhooks and syncs subscription
state into D1. All access-control decisions reference D1, not
the Stripe API, to avoid cold-start latency on every request.

## 1. Subscription Status State Machine

```
trial ──► active ──► past_due ──► canceled
  │          │            │
  │          │            └──► (dunning retries)
  │          │
  │          └──► canceled  (immediate cancel)
  │
  └──────────────────────────────► active (trial converts)
                                   (if payment method on file)

paused ◄──► active   (pause/resume for annual subscribers)
```

Map Stripe statuses to WAM internal statuses:

```
┌───────────────────┬─────────────────────────────────────┐
│ Stripe status     │ WAM internal                        │
├───────────────────┼─────────────────────────────────────┤
│ trialing          │ trial                               │
│ active            │ active                              │
│ past_due          │ grace (limited feature access)      │
│ unpaid            │ locked                              │
│ canceled          │ canceled                            │
│ paused            │ paused                              │
└───────────────────┴─────────────────────────────────────┘
```

## 2. Dunning Retry Schedule

Configure via Stripe's Smart Retries or a fixed schedule. Fixed
schedules are predictable for support teams; Smart Retries
improve recovery rates by 12–18 % on average.

Fixed schedule (configure in Billing settings):

```
Attempt 1 → day 0  (initial renewal failure)
Attempt 2 → day 1
Attempt 3 → day 3
Attempt 4 → day 5
Attempt 5 → day 7  → mark subscription unpaid, lock user
```

After attempt 5 with no recovery, set
`subscription.collection_method = "send_invoice"` so the
user can pay manually via a hosted link before cancellation.

Send email on each failure event. Map webhook events:

```
invoice.payment_failed   → log attempt N, send dunning email
invoice.payment_succeeded → clear past_due, restore access
customer.subscription.updated (status→unpaid) → lock account
```

## 3. Stripe Smart Retries

Enable in the Stripe Dashboard under
Settings → Billing → Automatic collection.

Smart Retries use Stripe ML to find the highest-probability
payment window (often weekday mornings in the card's timezone).
They replace the fixed schedule but honour the outer deadline
you set (7 days by default on WAM).

```typescript
// Check retry count from invoice metadata
async function handlePaymentFailed(invoice: Stripe.Invoice) {
  const sub = invoice.subscription as string;
  const attemptCount = invoice.attempt_count;
  const daysInGrace = 7;

  if (attemptCount >= 4) {
    // warn: approaching lock
    await sendEmail(invoice.customer_email!, "final_warning");
  }

  // After Stripe marks subscription unpaid, Workers webhook
  // sets WAM status to locked
  await env.DB.prepare(
    `UPDATE subscriptions SET status = 'grace',
     grace_attempt = ?, updated_at = ?
     WHERE stripe_sub_id = ?`,
  ).bind(attemptCount, Date.now(), sub).run();
}
```

## 4. Grace Period Design

During `past_due`, WAM grants a grace period so users are not
immediately locked out on the first retry attempt.

```
┌──────────────────────┬───────────────────────────────────┐
│ State                │ Access                            │
├──────────────────────┼───────────────────────────────────┤
│ active               │ Full feature access               │
│ trial                │ Full feature access               │
│ grace (past_due)     │ Read-only, no new purchases       │
│ locked (unpaid)      │ Login only, nudge to update card  │
│ canceled             │ No access; data retained 90 days  │
└──────────────────────┴───────────────────────────────────┘
```

Access control in Workers:

```typescript
function canAccessContent(sub: SubscriptionRow): boolean {
  return sub.status === "active" || sub.status === "trial"
    || sub.status === "grace";
}

function canPurchase(sub: SubscriptionRow): boolean {
  return sub.status === "active" || sub.status === "trial";
}
```

## 5. Cancellation Flows

Two modes:

**Immediate cancellation** — prorate refund, access ends now.
Use for fraud/ToS violations only.

```typescript
await stripe.subscriptions.cancel(subId, { prorate: true });
```

**End-of-period cancellation** — access continues until
`current_period_end`. This is the default UX flow.

```typescript
await stripe.subscriptions.update(subId, {
  cancel_at_period_end: true,
});
```

On `customer.subscription.deleted` webhook, set D1 status
to `canceled` and schedule a 90-day data-retention job.

**Reactivation after end-of-period cancellation** (before
the period ends):

```typescript
await stripe.subscriptions.update(subId, {
  cancel_at_period_end: false,
});
```

**Reactivation after cancellation** (new subscription):

```typescript
await stripe.subscriptions.create({
  customer: customerId,
  items: [{ price: priceId }],
  trial_end: "now", // no free trial on reactivation
});
```

## 6. Metered Billing — report_usage

For pay-per-message or pay-per-unlock features:

```typescript
// Report usage at end of billing period or on event
async function reportUsage(
  subscriptionItemId: string,
  quantity: number,
) {
  await stripe.subscriptionItems.createUsageRecord(
    subscriptionItemId,
    {
      quantity,
      timestamp: Math.floor(Date.now() / 1000),
      action: "increment",
    },
  );
}
```

Aggregate usage in D1 and report in batches every hour via a
Cloudflare Cron Trigger to avoid hitting the Stripe rate limit
(100 RPS per account).

## 7. Invoice Finalization Webhooks

```
invoice.created          → draft invoice, do not act yet
invoice.finalized        → invoice is locked; safe to display
invoice.payment_succeeded→ grant/extend access
invoice.payment_failed   → start dunning flow
invoice.paid             → alias for payment_succeeded on
                           send_invoice subscriptions
```

Never grant access on `invoice.created` — it fires before
payment. Use `invoice.payment_succeeded` or
`invoice.paid` exclusively as the trigger for provisioning.

## Anti-patterns

- Polling `stripe.subscriptions.retrieve` on every API request
  to check status — read from D1 instead; sync via webhooks.
- Canceling immediately on first payment failure — converts
  recoverable churn into permanent churn.
- Storing `current_period_end` as a Unix timestamp and
  comparing locally — time zones and Stripe's 1-hour invoice
  finalization window create race conditions.
- Setting `cancel_at_period_end: true` then also calling
  `stripe.subscriptions.cancel` — double-cancel produces a
  Stripe error on some SDK versions.

## Gotchas

- `invoice.payment_failed` fires before the retry schedule
  starts. `attempt_count` on the invoice tells you which
  attempt just failed (1-indexed).
- Stripe webhook events can arrive out of order. Always
  check `created` timestamp before writing status to D1.
- `subscription.pause_collection` pauses billing but keeps
  the subscription active; access during pause is a product
  decision, not a Stripe constraint.
- Metered billing usage records must be submitted before the
  invoice finalizes (roughly 1 hour before period end).
  Missed reports cannot be retroactively billed.

## Verification

```bash
# Simulate payment failure on a test subscription
stripe trigger invoice.payment_failed \
  --override invoice:subscription=sub_TEST

# Check D1 sync
wrangler d1 execute wam-db \
  --command "SELECT stripe_sub_id, status, updated_at
             FROM subscriptions ORDER BY updated_at DESC
             LIMIT 10"
```

Confirm that a `payment_failed` webhook transitions the D1
row to `grace` within 500 ms and that a re-fetch of the
protected route returns HTTP 200 (not 403) during grace.

## Related

- `stripe-connect-marketplace-platform-payments.md`
- `payment-fraud-detection-velocity-checks.md`
- `pci-dss-scope-reduction-tokenization.md`

## Source URLs (verified 2026-08-17)

- https://stripe.com/docs/billing/subscriptions/overview
- https://stripe.com/docs/billing/revenue-recovery/smart-retries
- https://stripe.com/docs/billing/subscriptions/pause-payment
- https://stripe.com/docs/billing/subscriptions/usage-based
- https://stripe.com/docs/billing/invoices/subscription
