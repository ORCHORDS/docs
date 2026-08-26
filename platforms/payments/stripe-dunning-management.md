# stripe-dunning-management

**Issue:** Configuring dunning to recover failed subscription payments in Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When a subscription payment fails, Stripe retries automatically, but you also need to notify customers and control when to cancel vs. keep retrying.

## Pattern / Solution
Configure in Dashboard > Settings > Billing > Subscriptions and emails:
- Smart Retries: on (Stripe ML-optimized timing)
- Retry schedule: Day 0, Day 3, Day 5, Day 7
- After all retries fail: mark subscription as `canceled` or `unpaid`

Listen to these webhooks:
```typescript
// invoice.payment_failed -> send customer email with payment link
// customer.subscription.updated (status: past_due) -> flag in your DB
// invoice.payment_action_required -> send 3DS action email
// customer.subscription.deleted -> revoke access
```

Hosted invoice page URL for customer recovery:
```typescript
const invoice = await stripe.invoices.retrieve(invoiceId);
const paymentLink = invoice.hosted_invoice_url;
```

## Gotchas
- Do not revoke access on `invoice.payment_failed` — wait for final retry cycle
- `past_due` subscriptions still have active access by default
- Smart Retries respects card network recommendations; do not override with aggressive manual retries
- `invoice.payment_action_required` means 3DS is needed, not that payment failed

## Related
- `stripe-failed-payment-retry.md`
- `stripe-smart-retries.md`
- `stripe-payment-recovery-emails.md`
