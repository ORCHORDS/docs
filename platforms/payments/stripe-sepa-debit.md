# stripe-sepa-debit

**Issue:** Accepting SEPA Direct Debit payments via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SEPA Direct Debit enables bank account pulls for EU customers, commonly used for subscriptions in Germany, France, Netherlands, and other SEPA countries.

## Pattern / Solution
```typescript
// Collect IBAN and create SetupIntent for recurring use
const setupIntent = await stripe.setupIntents.create({
  payment_method_types: ['sepa_debit'],
  customer: customerId,
});

// Client: confirm the SetupIntent with IBAN
const { error, setupIntent: confirmed } = await stripe.confirmSepaDebitSetup(
  clientSecret,
  {
    payment_method: {
      sepa_debit: { iban: 'DE89370400440532013000' },
      billing_details: { name: 'Customer Name', email: 'customer@example.com' },
    },
  }
);

// Then use the payment method for subscriptions
await stripe.subscriptions.create({
  customer: customerId,
  items: [{ price: priceId }],
  default_payment_method: confirmed.payment_method,
});
```

## Gotchas
- SEPA payments can take 5-7 business days to settle — do not provision immediately
- A mandate must be shown to the customer before collecting IBAN — Stripe handles this
- SEPA refunds can take up to 8 weeks for the customer to receive
- Disputes on SEPA are more complex than card disputes

## Related
- `stripe-bacs-debit.md`
- `stripe-acss-debit.md`
- `stripe-bank-transfer.md`
