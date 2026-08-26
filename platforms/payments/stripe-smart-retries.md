# stripe-smart-retries

**Issue:** Using Stripe Smart Retries to optimize failed payment recovery
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe uses machine learning to predict the optimal time to retry a declined card, improving recovery rates versus fixed retry schedules.

## Pattern / Solution
Enable in Dashboard > Settings > Billing > Subscriptions and emails > Smart Retries: ON.

No code change required — Stripe handles retry timing automatically. You receive webhooks:
```typescript
// Stripe retries at ML-optimized intervals (typically within 7 days)
// invoice.payment_failed fires on each failed attempt
// invoice.paid fires on successful recovery

// Your job: send dunning emails and update UI state
switch (event.type) {
  case 'invoice.payment_failed':
    const invoice = event.data.object;
    const attemptCount = invoice.attempt_count;
    await sendDunningEmail(invoice.customer_email, attemptCount);
    break;
}
```

## Gotchas
- Smart Retries only applies to subscription invoices, not one-time PaymentIntents
- You cannot control the exact retry timing with Smart Retries enabled
- Disable Smart Retries if you need exact retry windows for compliance reasons
- Recovery rates vary by card network; American Express has different decline codes than Visa

## Related
- `stripe-dunning-management.md`
- `stripe-failed-payment-retry.md`
- `stripe-payment-recovery-emails.md`
