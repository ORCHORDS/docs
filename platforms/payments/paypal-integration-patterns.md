# paypal-integration-patterns

**Issue:** Integrating PayPal payments alongside Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Many customers prefer PayPal. Adding it alongside Stripe (or as an alternative) can increase conversion, especially for international customers who distrust card entry.

## Pattern / Solution
```typescript
// Server: create PayPal order
const response = await fetch('https://api-m.paypal.com/v2/checkout/orders', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    intent: 'CAPTURE',
    purchase_units: [{
      amount: { currency_code: 'USD', value: '29.00' },
      reference_id: orderId,
    }],
  }),
});
const order = await response.json();

// Client: render PayPal buttons
paypal.Buttons({
  createOrder: () => order.id,
  onApprove: async (data) => {
    await captureOrder(data.orderID);
  },
}).render('#paypal-button-container');
```

## Gotchas
- PayPal access tokens expire every 9 hours — cache and refresh proactively
- Capture must happen server-side after `onApprove` fires — never trust client-side only
- PayPal webhooks use different signature verification than Stripe
- Sandbox vs. production uses different API base URLs
- PayPal Checkout v2 (REST) is the current API; avoid the legacy NVP/SOAP API

## Related
- `paypal-subscriptions.md`
- `paypal-webhooks.md`
- `payment-provider-abstraction.md`
