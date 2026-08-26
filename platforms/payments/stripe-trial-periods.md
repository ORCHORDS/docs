# stripe-trial-periods

**Issue:** Implementing free trial periods with Stripe subscriptions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You want users to try the product for N days before billing begins. Stripe supports trials natively on subscriptions with configurable end behavior.

## Pattern / Solution
```typescript
const subscription = await stripe.subscriptions.create({
  customer: customerId,
  items: [{ price: 'price_xxx' }],
  trial_period_days: 14,
  trial_settings: {
    end_behavior: { missing_payment_method: 'pause' }, // or 'cancel'
  },
});
```

To require a card upfront with trial via Checkout:
```typescript
{
  mode: 'subscription',
  payment_method_collection: 'always',
  subscription_data: { trial_period_days: 14 }
}
```

## Gotchas
- Without a payment method, set `end_behavior.missing_payment_method: 'cancel'` or `'pause'`
- `trialing` subscriptions emit `customer.subscription.trial_will_end` 3 days before expiry
- Trial extensions: update `trial_end` to a future Unix timestamp on the subscription
- Trials with no card attached and `pause` behavior create an odd UX — prefer requiring card

## Related
- `stripe-subscription-lifecycle.md`
- `free-trial-credit-card-required.md`
- `dunning-email-sequences.md`
