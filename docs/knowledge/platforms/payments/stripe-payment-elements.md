# stripe-payment-elements

**Issue:** Embedding Stripe Payment Elements for a unified payment UI
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Payment Element replaces the old CardElement and supports 40+ payment methods from a single component with adaptive UI that selects methods based on customer location.

## Pattern / Solution
```javascript
const stripe = Stripe(PUBLISHABLE_KEY);
const elements = stripe.elements({ clientSecret });
const paymentElement = elements.create('payment', {
  layout: 'tabs', // or 'accordion'
});
paymentElement.mount('#payment-element');

// On form submit
const { error } = await stripe.confirmPayment({
  elements,
  confirmParams: { return_url: window.location.origin + '/complete' },
});
```

## Gotchas
- Must pass `clientSecret` from your server when creating `elements()`
- `layout: 'tabs'` groups methods; `'accordion'` shows one at a time
- The element's iframe handles PCI scope — never touch card numbers directly
- Appearance API lets you theme the element to match your design system via CSS variables

## Related
- `stripe-payment-intents.md`
- `stripe-apple-pay-setup.md`
- `stripe-google-pay-setup.md`
