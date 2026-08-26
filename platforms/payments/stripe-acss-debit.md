# stripe-acss-debit

**Issue:** Accepting ACSS (Canadian) Direct Debit payments via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ACSS (Automated Clearing Settlement System) is the Canadian equivalent of ACH/SEPA for pre-authorized bank debits.

## Pattern / Solution
```typescript
const setupIntent = await stripe.setupIntents.create({
  payment_method_types: ['acss_debit'],
  customer: customerId,
  payment_method_options: {
    acss_debit: {
      currency: 'cad',
      mandate_options: {
        payment_schedule: 'combined',
        transaction_type: 'business',
      },
    },
  },
});
```

Stripe displays a mandate agreement UI via the SetupIntent confirmation flow.

## Gotchas
- Requires customer to go through a bank verification flow (micro-deposits or instant verification)
- Available in CAD only
- Settlement takes 5 business days typically
- Mandate options: `payment_schedule` can be `'interval'`, `'sporadic'`, or `'combined'`
- Return code handling is important — track `payment_intent.payment_failed` for NSF returns

## Related
- `stripe-sepa-debit.md`
- `stripe-bacs-debit.md`
