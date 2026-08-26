# stripe-link-payment-method

**Issue:** Integrating Stripe Link for one-click checkout returning customers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe Link saves customer payment details across merchants. Returning Link users can pay with one click using their saved card or bank account.

## Pattern / Solution
Link is enabled automatically via Payment Element:
```typescript
const elements = stripe.elements({
  clientSecret,
  appearance,
});
// Link appears automatically for eligible customers
```

Optimize Link by pre-filling customer email:
```typescript
const elements = stripe.elements({
  clientSecret,
  appearance,
  loader: 'auto',
});
const paymentElement = elements.create('payment', {
  defaultValues: { billingDetails: { email: user.email } },
});
```

## Gotchas
- Link requires `automatic_payment_methods: { enabled: true }` on the PaymentIntent
- Link is cross-merchant — customer's saved card from another Stripe merchant is available
- Cannot disable Link without disabling Payment Element's automatic method selection
- Link authentication happens via SMS or email OTP — customers must have a Link account

## Related
- `stripe-payment-elements.md`
- `stripe-checkout-session.md`
