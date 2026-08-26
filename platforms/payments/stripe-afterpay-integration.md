# stripe-afterpay-integration

**Issue:** Integrating Afterpay/Clearpay BNPL via Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Afterpay (US/AU/CA) / Clearpay (UK/EU) splits payments into four equal installments. Popular with younger demographics in fashion and lifestyle verticals.

## Pattern / Solution
```typescript
const intent = await stripe.paymentIntents.create({
  amount: 15000, // $150.00
  currency: 'usd',
  payment_method_types: ['afterpay_clearpay'],
  shipping: {
    address: { line1: '123 Main St', city: 'Austin', state: 'TX', postal_code: '78701', country: 'US' },
    name: 'Customer Name',
  },
});
```

Via Payment Element: Afterpay appears automatically when customer and amount qualify.

## Gotchas
- Shipping address is required for Afterpay — cannot be used for digital goods in some regions
- Amount limits vary by country (typically $1 to $2,000 in the US)
- Not available for subscriptions
- The brand name changes by region: Afterpay in US/AU/CA, Clearpay in UK/EU
- Refunds are issued to Afterpay who handles the installment adjustment

## Related
- `stripe-klarna-bnpl.md`
- `stripe-payment-elements.md`
