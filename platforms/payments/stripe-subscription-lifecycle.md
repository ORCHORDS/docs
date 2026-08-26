# stripe-subscription-lifecycle

**Issue:** Understanding Stripe subscription states and transitions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Subscriptions move through states: incomplete, active, past_due, canceled, unpaid. Missing a state transition causes access control bugs where users lose or retain access incorrectly.

## Pattern / Solution
```typescript
// Listen for these webhook events in order:
// customer.subscription.created  -> provision access
// customer.subscription.updated  -> handle plan changes
// customer.subscription.deleted  -> revoke access
// invoice.payment_failed         -> begin dunning
// invoice.paid                   -> confirm renewal

function getAccess(sub: Stripe.Subscription): boolean {
  return ['active', 'trialing'].includes(sub.status);
}
```

## Gotchas
- `incomplete` means the first payment failed — do not provision access yet
- `past_due` still has access by default — configure Smart Retries before canceling
- `cancel_at_period_end: true` means the subscription is still `active` until the period ends
- Deleted subscriptions emit `customer.subscription.deleted`, not `updated`

## Related
- `stripe-dunning-management.md`
- `stripe-failed-payment-retry.md`
- `stripe-cancellation-flow.md`
