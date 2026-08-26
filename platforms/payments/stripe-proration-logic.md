# stripe-proration-logic

**Issue:** Understanding and controlling Stripe proration behavior on plan changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When a customer upgrades or downgrades mid-cycle, Stripe calculates a prorated credit or charge. Misconfiguring this leads to unexpected invoice amounts.

## Pattern / Solution
```typescript
// Preview proration before applying
const preview = await stripe.invoices.retrieveUpcoming({
  customer: customerId,
  subscription: subscriptionId,
  subscription_items: [
    { id: subscriptionItemId, price: newPriceId }
  ],
  subscription_proration_date: Math.floor(Date.now() / 1000),
});
const prorationAmount = preview.amount_due;

// Apply the change
await stripe.subscriptions.update(subscriptionId, {
  items: [{ id: subscriptionItemId, price: newPriceId }],
  proration_behavior: 'create_prorations', // immediate credit/charge
});
```

## Gotchas
- `'always_invoice'` immediately creates and pays a proration invoice
- `'none'` skips proration — customer gets the new plan but no credit or charge
- `'create_prorations'` adds credits to the next invoice — nothing is charged immediately
- Always preview before applying to show the customer what they will pay

## Related
- `stripe-upgrade-downgrade.md`
- `stripe-billing-anchor-dates.md`
