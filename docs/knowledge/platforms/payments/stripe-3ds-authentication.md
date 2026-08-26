# stripe-3ds-authentication

**Issue:** Handling 3D Secure authentication in Stripe payment flows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
European regulations (SCA/PSD2) require strong customer authentication for many payments. 3DS adds a bank-side verification step that Stripe handles automatically with Payment Intents.

## Pattern / Solution
```typescript
// Server: create PaymentIntent with SCA support
const intent = await stripe.paymentIntents.create({
  amount: 5000,
  currency: 'eur',
  automatic_payment_methods: { enabled: true },
  // Stripe handles 3DS automatically
});

// Client: confirmPayment redirects to bank if 3DS needed
const { error } = await stripe.confirmPayment({
  elements,
  confirmParams: { return_url: 'https://example.com/complete' },
});

// After return_url redirect, check status
const { paymentIntent } = await stripe.retrievePaymentIntent(clientSecret);
if (paymentIntent.status === 'succeeded') { /* fulfill */ }
```

## Gotchas
- `requires_action` status means 3DS is pending, not that payment failed
- Off-session payments (renewals) can fail 3DS — send authentication email to customer
- Use `payment_method_options.card.request_three_d_secure: 'automatic'` for optimal balance
- Exemptions: low-value transactions under EUR 30 may be exempt from SCA

## Related
- `stripe-payment-intents.md`
- `stripe-radar-fraud-rules.md`
