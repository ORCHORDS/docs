# stripe-google-pay-setup

**Issue:** Enabling Google Pay in Stripe payment flows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Google Pay works on Android and Chrome across all platforms. It enables one-tap checkout using stored Google Wallet cards.

## Pattern / Solution
Google Pay appears automatically in Payment Element with no extra configuration needed.

For the Payment Request Button (legacy approach):
```javascript
const paymentRequest = stripe.paymentRequest({
  country: 'US',
  currency: 'usd',
  total: { label: 'Total', amount: 1999 },
  requestPayerName: true,
  requestPayerEmail: true,
});

const canMakePayment = await paymentRequest.canMakePayment();
if (canMakePayment?.googlePay) {
  const prButton = elements.create('paymentRequestButton', { paymentRequest });
  prButton.mount('#payment-request-button');
}
```

## Gotchas
- Google Pay requires HTTPS in production but works on localhost in test mode
- `canMakePayment()` returns null if the user has no saved cards in Google Pay
- The Payment Request Button also shows Apple Pay on Safari — one element handles both
- No domain verification required for Google Pay (unlike Apple Pay)
- Google Pay is available in Chrome on Android and desktop

## Related
- `stripe-apple-pay-setup.md`
- `stripe-payment-elements.md`
