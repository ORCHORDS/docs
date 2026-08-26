# refund-policy-implementation

**Issue:** Implementing a self-serve refund flow that satisfies customers and reduces chargebacks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Making refunds difficult pushes customers to dispute charges with their bank, resulting in chargeback fees. A frictionless refund flow is cheaper than chargebacks.

## Pattern / Solution
Expose a refund button in the customer portal. Call Stripe POST /v1/refunds with the charge or payment_intent ID. Set reason to one of: duplicate, fraudulent, requested_by_customer. Email confirmation immediately. Handle partial refunds with amount parameter. Update your database on refund.succeeded webhook.

## Gotchas
Stripe refunds can fail if the card has been closed — funds are returned to the original payment method, but if unavailable, Stripe holds funds. Refunds for ACH payments take 5-10 business days. You cannot refund more than the original charge.

## Related
partial-refund-handling, chargeback-prevention, stripe-payment-intents
