# stripe-klarna-bnpl

**Issue:** Integrating Klarna Buy Now Pay Later via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Klarna lets customers pay in installments. Offering BNPL at checkout increases conversion, especially for higher-value purchases.

## Pattern / Solution
```typescript
// Enable via Payment Element (automatic)
const elements = stripe.elements({
  clientSecret,
  appearance: { theme: 'stripe' },
});
// Klarna appears automatically if customer location and currency are supported

// Or explicitly request Klarna on PaymentIntent
const intent = await stripe.paymentIntents.create({
  amount: 10000,
  currency: 'usd',
  payment_method_types: ['klarna'],
  payment_method_options: {
    klarna: { preferred_locale: 'en-US' },
  },
});
```

## Gotchas
- Klarna is only available in supported countries and currencies — check Stripe's docs
- Klarna payments cannot be partially captured
- Refunds for Klarna payments are processed back to Klarna (they handle customer refunds)
- Minimum and maximum order amounts apply per country
- Klarna is not available for subscription billing — one-time payments only

## Related
- `stripe-payment-elements.md`
- `stripe-afterpay-integration.md`
