# stripe-payment-recovery-emails

**Issue:** Sending payment recovery emails with hosted invoice links
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When a payment fails, customers need an email with a direct link to update their card and pay the outstanding invoice without logging in.

## Pattern / Solution
```typescript
// In invoice.payment_failed webhook handler
const invoice = event.data.object as Stripe.Invoice;
const hostedUrl = invoice.hosted_invoice_url; // tokenized, no login needed

await sendEmail({
  to: invoice.customer_email,
  subject: 'Action required: Update your payment method',
  html: `
    <p>Your payment of ${formatAmount(invoice.amount_due, invoice.currency)} failed.</p>
    <a >Update payment method</a>
    <p>Your access will continue until ${formatDate(invoice.next_payment_attempt)}.</p>
  `,
});
```

Stripe also sends its own automatic emails — disable them in Dashboard if you use custom emails to avoid duplication.

## Gotchas
- `hosted_invoice_url` is long-lived but can be regenerated if expired
- Disable Stripe's built-in payment failure emails in Dashboard > Settings > Emails if sending your own
- Include `attempt_count` context so customers know how many retries remain
- Link to the Customer Portal as an alternative for customers who prefer self-service

## Related
- `stripe-dunning-management.md`
- `stripe-smart-retries.md`
- `dunning-email-sequences.md`
