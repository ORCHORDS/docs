# stripe-virtual-bank-accounts

**Issue:** Issuing virtual bank accounts for customer balance top-ups via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
For platforms that maintain a customer balance (wallets, prepaid accounts), virtual bank accounts let customers wire money to a dedicated account that auto-credits their Stripe customer balance.

## Pattern / Solution
```typescript
// Fund a customer balance via bank transfer
const fundingInstructions = await stripe.customers.createFundingInstructions(
  customerId,
  {
    bank_transfer: {
      type: 'us_domestic_wire', // or 'eu_bank_transfer', 'gb_bank_transfer'
    },
    currency: 'usd',
    funding_type: 'bank_transfer',
  }
);

const instructions = fundingInstructions.bank_transfer.financial_addresses[0];
// instructions.aba.routing_number, instructions.aba.account_number
```

Listen for `customer.cash_balance.funds_available` webhook to credit the customer.

## Gotchas
- Virtual account numbers are permanent per customer per currency
- Stripe automatically applies incoming funds to the customer's cash balance
- You must then apply the cash balance to invoices or subscriptions manually
- Not all bank transfer types are available in all countries

## Related
- `stripe-bank-transfer.md`
- `wallet-balance-patterns.md`
