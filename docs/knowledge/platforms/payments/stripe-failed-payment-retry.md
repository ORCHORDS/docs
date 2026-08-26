# stripe-failed-payment-retry

**Issue:** Manually retrying failed invoices in Stripe
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You want to trigger a payment retry outside Stripe's automatic schedule, for example after a customer updates their payment method.

## Pattern / Solution
```typescript
// Retry payment on an invoice
await stripe.invoices.pay(invoiceId, {
  payment_method: newPaymentMethodId, // optional: use specific method
});

// Listen for the result
// invoice.paid -> success, update subscription status
// invoice.payment_failed -> retry failed

// Update default payment method before retrying
await stripe.customers.update(customerId, {
  invoice_settings: { default_payment_method: newPaymentMethodId },
});
await stripe.invoices.pay(invoiceId);
```

## Gotchas
- Retrying with the same declined card immediately is usually futile; prompt customer to update card first
- `invoices.pay` on an already paid invoice returns an error — check `invoice.status` first
- Manual retries count against Stripe's retry limits — use sparingly
- If `requires_action` is returned, the customer must complete 3DS authentication

## Related
- `stripe-dunning-management.md`
- `stripe-smart-retries.md`
- `card-expiry-handling.md`
