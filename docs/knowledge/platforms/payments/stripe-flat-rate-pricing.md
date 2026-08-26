# stripe-flat-rate-pricing

**Issue:** Setting up simple flat-rate recurring prices in Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The simplest pricing model: one fixed amount billed on a recurring schedule. Most SaaS products start here.

## Pattern / Solution
```typescript
const price = await stripe.prices.create({
  unit_amount: 2900, // $29.00
  currency: 'usd',
  recurring: { interval: 'month' },
  product: productId,
  nickname: 'Pro Monthly',
  lookup_key: 'pro_monthly', // stable reference
});
```

To attach to a subscription:
```typescript
await stripe.subscriptions.create({
  customer: customerId,
  items: [{ price: price.id }],
});
```

## Gotchas
- Prices are immutable after creation; create a new price and migrate customers when changing amount
- Use `lookup_key` on prices to reference them by a stable string from your code
- Archive old prices instead of deleting to preserve historical data integrity
- `transfer_lookup_key: true` moves the lookup key when creating a replacement price

## Related
- `stripe-tiered-pricing.md`
- `stripe-upgrade-downgrade.md`
