# stripe-coupon-discount

**Issue:** Applying coupons and promotional codes in Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You want to offer discounts via coupon codes during checkout or apply them programmatically to subscriptions.

## Pattern / Solution
```typescript
// Create a coupon
const coupon = await stripe.coupons.create({
  percent_off: 20,
  duration: 'repeating',
  duration_in_months: 3,
  name: 'LAUNCH20',
});

// Create a promotion code (customer-facing code)
const promoCode = await stripe.promotionCodes.create({
  coupon: coupon.id,
  code: 'LAUNCH20',
  max_redemptions: 100,
});

// Apply to subscription
await stripe.subscriptions.create({
  customer: customerId,
  items: [{ price: priceId }],
  discounts: [{ promotion_code: promoCode.id }],
});
```

## Gotchas
- Coupons are the discount definition; promotion codes are the redeemable strings customers enter
- `duration: 'once'` applies to first invoice only; `'forever'` applies indefinitely
- A subscription can have at most one discount at a time unless using multiple coupons via `discounts` array
- Coupon deletion does not remove existing discounts from subscriptions

## Related
- `stripe-flat-rate-pricing.md`
- `stripe-customer-portal.md`
