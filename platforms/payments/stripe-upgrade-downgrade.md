# stripe-upgrade-downgrade

**Issue:** Handling plan upgrades and downgrades in Stripe subscriptions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Customers switching between plans mid-cycle need prorated billing and immediate access changes, without creating a new subscription.

## Pattern / Solution
```typescript
// Get current subscription item ID
const subscription = await stripe.subscriptions.retrieve(subscriptionId);
const itemId = subscription.items.data[0].id;

// Upgrade immediately with proration
await stripe.subscriptions.update(subscriptionId, {
  items: [{ id: itemId, price: newPriceId }],
  proration_behavior: 'always_invoice', // charge/credit immediately
});

// Downgrade at period end (no proration, no immediate charge)
await stripe.subscriptions.update(subscriptionId, {
  items: [{ id: itemId, price: lowerPriceId }],
  proration_behavior: 'none',
  billing_cycle_anchor: 'unchanged',
});
```

## Gotchas
- For upgrades, use `'always_invoice'` to charge the customer immediately
- For downgrades, `'none'` with no anchor change is less confusing for customers
- Update your database access tier in the `customer.subscription.updated` webhook, not the API response
- If multiple items exist, update each item individually

## Related
- `stripe-proration-logic.md`
- `stripe-subscription-lifecycle.md`
- `stripe-customer-portal.md`
