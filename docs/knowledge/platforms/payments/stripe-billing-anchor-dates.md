# stripe-billing-anchor-dates

**Issue:** Controlling subscription billing dates with anchor dates in Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
By default subscriptions bill from the creation date. Anchor dates let you normalize all customers to bill on the same day of the month (e.g., the 1st).

## Pattern / Solution
```typescript
// Bill on the 1st of each month regardless of signup date
const anchorDate = new Date();
anchorDate.setMonth(anchorDate.getMonth() + 1);
anchorDate.setDate(1);
anchorDate.setHours(0, 0, 0, 0);

const subscription = await stripe.subscriptions.create({
  customer: customerId,
  items: [{ price: priceId }],
  billing_cycle_anchor: Math.floor(anchorDate.getTime() / 1000),
  proration_behavior: 'create_prorations',
});
```

## Gotchas
- Stripe prorates the period from signup to anchor date automatically when `proration_behavior: 'create_prorations'`
- `proration_behavior: 'none'` gives a free partial period — consider this for simplicity
- Anchor date must be in the future
- Changing anchor date mid-subscription triggers a proration invoice

## Related
- `stripe-proration-logic.md`
- `stripe-subscription-lifecycle.md`
