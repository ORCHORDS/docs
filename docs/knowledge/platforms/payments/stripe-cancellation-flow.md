# stripe-cancellation-flow

**Issue:** Implementing a proper cancellation flow with Stripe subscriptions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Immediate cancellation vs. end-of-period cancellation have different business impacts on revenue and access. Most SaaS products should use end-of-period by default.

## Pattern / Solution
```typescript
// Cancel at end of billing period (recommended for SaaS)
await stripe.subscriptions.update(subscriptionId, {
  cancel_at_period_end: true,
});

// Immediate cancellation with refund
await stripe.subscriptions.cancel(subscriptionId, {
  invoice_now: false,
  prorate: false,
});

// Reverse a scheduled cancellation
await stripe.subscriptions.update(subscriptionId, {
  cancel_at_period_end: false,
});
```

## Gotchas
- `cancel_at_period_end: true` leaves the subscription in `active` state — keep granting access
- `customer.subscription.deleted` fires when the subscription actually ends, not when cancellation is scheduled
- Immediately canceled subscriptions do NOT generate a final invoice unless `invoice_now: true`
- Store `cancel_at` timestamp to show the user when access expires

## Related
- `stripe-subscription-lifecycle.md`
- `stripe-reactivation-patterns.md`
- `stripe-dunning-management.md`
