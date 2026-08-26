# stripe-payment-intents

**Issue:** Using Payment Intents API for custom payment flows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Checkout is too opinionated; you need full control over the UI and confirmation flow while still handling 3DS and payment method routing.

## Pattern / Solution
```typescript
// Server: create intent
const intent = await stripe.paymentIntents.create({
  amount: 2000, // cents
  currency: 'usd',
  automatic_payment_methods: { enabled: true },
  metadata: { orderId: '123' },
});
return { clientSecret: <redacted-secret> };

// Client: confirm
const { error } = await stripe.confirmPayment({
  elements,
  confirmParams: { return_url: 'https://example.com/complete' },
});
```

## Gotchas
- Amount is always in the smallest currency unit (cents for USD, pence for GBP)
- `automatic_payment_methods` is preferred over listing methods manually
- Capture happens automatically unless you set `capture_method: 'manual'`
- A PaymentIntent in `requires_action` state is not failed — poll or use webhooks to track it

## Related
- `stripe-payment-elements.md`
- `stripe-3ds-authentication.md`
