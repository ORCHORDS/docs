# stripe-tax-calculation

**Issue:** Automatic tax calculation with Stripe Tax
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You need to charge the correct sales tax or VAT without building a tax engine. Stripe Tax handles rate lookup and nexus determination.

## Pattern / Solution
```typescript
// Enable on PaymentIntent
const intent = await stripe.paymentIntents.create({
  amount: 1000,
  currency: 'usd',
  automatic_tax: { enabled: true },
  customer: customerId, // customer must have address
});

// Enable on Checkout Session
const session = await stripe.checkout.sessions.create({
  automatic_tax: { enabled: true },
  // ...
});

// Enable on Subscription
await stripe.subscriptions.create({
  automatic_tax: { enabled: true },
  // ...
});
```

## Gotchas
- Requires the customer to have a valid address set before tax calculation
- You must register your nexus in Stripe Dashboard before tax is applied
- Stripe Tax adds a line item on the invoice — verify your invoice template shows it clearly
- Not available in all countries; check Stripe's supported regions list

## Related
- `vat-calculation-eu.md`
- `sales-tax-us-states.md`
- `stripe-invoice-customization.md`
