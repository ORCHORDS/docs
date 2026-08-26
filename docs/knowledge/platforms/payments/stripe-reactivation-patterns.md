# stripe-reactivation-patterns

**Issue:** Reactivating canceled or paused Stripe subscriptions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Customers who canceled and want to come back should not need to go through full signup again. Stripe supports reactivation for end-of-period cancellations and paused subscriptions.

## Pattern / Solution
```typescript
// Reactivate before period end (cancel_at_period_end: true case)
await stripe.subscriptions.update(subscriptionId, {
  cancel_at_period_end: false,
});

// Resume a paused subscription
await stripe.subscriptions.resume(subscriptionId, {
  billing_cycle_anchor: 'now', // or 'unchanged'
});

// Reactivate a fully canceled subscription (create new)
await stripe.subscriptions.create({
  customer: existingCustomerId, // reuse existing customer
  items: [{ price: priceId }],
  default_payment_method: storedPaymentMethodId,
});
```

## Gotchas
- Once a subscription reaches `canceled` status it cannot be un-canceled — create a new one
- Reuse the existing Stripe customer ID to preserve payment methods and billing history
- Check for stored `default_payment_method` on the customer before creating a new subscription
- Winback emails should link directly to a Checkout session pre-populated with the customer's email

## Related
- `stripe-cancellation-flow.md`
- `stripe-dunning-management.md`
- `freemium-to-paid-conversion.md`
