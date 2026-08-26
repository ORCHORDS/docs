# stripe-tiered-pricing

**Issue:** Configuring tiered pricing in Stripe for volume-based billing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Price changes based on quantity: first 100 units at $1, next 900 at $0.80, etc. Common for API products and seat-based SaaS.

## Pattern / Solution
```typescript
const price = await stripe.prices.create({
  currency: 'usd',
  recurring: { interval: 'month', usage_type: 'metered', aggregate_usage: 'sum' },
  billing_scheme: 'tiered',
  tiers_mode: 'graduated', // or 'volume'
  tiers: [
    { up_to: 100, unit_amount: 100 },
    { up_to: 1000, unit_amount: 80 },
    { up_to: 'inf', unit_amount: 50 },
  ],
  product: productId,
});
```

## Gotchas
- `graduated`: each tier applies to units in that range — most common and most intuitive
- `volume`: the entire quantity is priced at the tier the total quantity falls into
- Add a `flat_amount` to a tier for a base fee at that level
- Tiers must be in ascending order with the last tier having `up_to: 'inf'`
- Tiered prices must have `billing_scheme: 'tiered'`

## Related
- `stripe-metered-billing.md`
- `stripe-usage-based-billing.md`
