# stripe-bacs-debit

**Issue:** Accepting BACS Direct Debit for UK customers via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
BACS Direct Debit is the standard payment method for recurring billing in the UK. Required for UK enterprise customers who prefer bank account debits over cards.

## Pattern / Solution
```typescript
const setupIntent = await stripe.setupIntents.create({
  payment_method_types: ['bacs_debit'],
  customer: customerId,
});

// Client: confirm with sort code and account number
const { setupIntent: confirmed } = await stripe.confirmBacsDebitSetup(clientSecret, {
  payment_method: {
    bacs_debit: {
      sort_code: '108800',
      account_number: '00012345',
    },
    billing_details: {
      name: 'Customer Name',
      email: 'customer@example.com',
      address: { line1: '123 High St', city: 'London', postal_code: 'SW1A 1AA', country: 'GB' },
    },
  },
});
```

## Gotchas
- BACS requires a 3-day advance notice period before the first debit
- Payments take 3-5 business days to settle
- A confirmation email with the mandate is sent automatically by Stripe to the customer
- BACS is only available in GBP for UK accounts
- Stripe requires your company to be set up with Bacs Payment Schemes Limited via Stripe

## Related
- `stripe-sepa-debit.md`
- `stripe-acss-debit.md`
