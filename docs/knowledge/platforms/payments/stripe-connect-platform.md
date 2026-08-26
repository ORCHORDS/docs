# stripe-connect-platform

**Issue:** Building a Stripe Connect platform to process payments for connected accounts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You are building a marketplace or SaaS platform where third parties receive payments. Stripe Connect routes funds between your platform and connected accounts.

## Pattern / Solution
```typescript
// Charge on behalf of connected account
const paymentIntent = await stripe.paymentIntents.create({
  amount: 10000,
  currency: 'usd',
  application_fee_amount: 500, // your platform fee
  transfer_data: {
    destination: connectedAccountId, // acct_xxx
  },
});

// Or: create charge directly on connected account (using Stripe-Account header)
const stripeOnBehalf = new Stripe(secretKey, { stripeAccount: connectedAccountId });
const charge = await stripeOnBehalf.charges.create({ amount: 10000, currency: 'usd' });
```

## Gotchas
- Destination charges keep funds on the platform then transfer; direct charges keep funds on connected account
- Application fee is taken from the transfer amount before it reaches the connected account
- Platform is liable for refunds on destination charges
- Webhook events for connected accounts require listening to the `account` param in the event

## Related
- `stripe-connect-express.md`
- `stripe-connect-custom.md`
- `stripe-connect-payouts.md`
