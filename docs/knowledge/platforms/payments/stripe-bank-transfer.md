# stripe-bank-transfer

**Issue:** Accepting bank transfer payments via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Bank transfers are preferred by B2B customers for large invoices. Stripe can issue virtual bank account numbers that customers wire to, with automatic reconciliation.

## Pattern / Solution
```typescript
// Create a PaymentIntent with bank transfer
const paymentIntent = await stripe.paymentIntents.create({
  amount: 100000, // $1,000.00
  currency: 'usd',
  payment_method_types: ['us_bank_account'],
  payment_method_options: {
    us_bank_account: {
      financial_connections: { permissions: ['payment_method'] },
    },
  },
});

// Or for manual bank transfer (invoice-based)
const invoice = await stripe.invoices.create({
  customer: customerId,
  payment_settings: {
    payment_method_types: ['customer_balance'],
  },
});
await stripe.invoices.finalizeInvoice(invoice.id);
// Customer sees bank transfer instructions in hosted invoice
```

## Gotchas
- Bank transfers take 1-5 business days to arrive and reconcile
- Virtual bank account numbers are customer-specific — do not share between customers
- Overpayments create a credit balance on the customer; underpayments leave the invoice partially paid
- ACH Credits (pushes) have no SLA; ACH Debits (pulls) have specific return windows

## Related
- `stripe-virtual-bank-accounts.md`
- `stripe-sepa-debit.md`
