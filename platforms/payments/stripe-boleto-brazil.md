# stripe-boleto-brazil

**Issue:** Accepting Boleto payments for Brazilian customers via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Boleto Bancario is a cash-based payment voucher widely used in Brazil. Customers receive a voucher and pay at a bank, ATM, or online banking within a set deadline.

## Pattern / Solution
```typescript
const paymentIntent = await stripe.paymentIntents.create({
  amount: 10000,
  currency: 'brl',
  payment_method_types: ['boleto'],
  payment_method_data: {
    type: 'boleto',
    boleto: { tax_id: '000.000.000-00' }, // CPF or CNPJ
    billing_details: {
      name: 'Customer Name',
      email: 'customer@example.com',
      address: { line1: 'Rua Example 123', city: 'Sao Paulo', state: 'SP', postal_code: '01310-100', country: 'BR' },
    },
  },
  confirm: true,
  return_url: 'https://example.com/complete',
});

// Retrieve boleto voucher URL from next_action
const voucherUrl = paymentIntent.next_action?.boleto_display_details?.hosted_voucher_url;
```

## Gotchas
- Boleto expires after a configurable period (default 3 days); set `expires_after_days`
- Payment confirmation takes 1-3 business days after the customer pays
- Tax ID (CPF for individuals, CNPJ for businesses) is mandatory
- No refund mechanism — issue bank transfer refunds manually outside Stripe
- Not available for subscriptions

## Related
- `stripe-pix-brazil.md`
- `payment-provider-abstraction.md`
