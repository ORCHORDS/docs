# receipt-email-template

**Issue:** Designing transactional receipt emails that comply with payment regulations and reduce disputes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Customers who do not recognize a charge file chargebacks. Receipt emails with clear merchant identity, amount, and description significantly reduce friendly-fraud disputes.

## Pattern / Solution
Send receipt emails immediately after successful payment via Stripe webhook (payment_intent.succeeded or invoice.paid). Include: merchant name, support email, charge amount and currency, last 4 digits of card, description of what was purchased, billing period for subscriptions, and a refund policy link.

## Gotchas
Match the receipt merchant name to the statement descriptor to prevent unrecognized charge disputes. For subscriptions, remind users of the next billing date. Include a one-click cancel link to reduce chargebacks.

## Related
stripe-dunning-management, chargeback-prevention, stripe-payment-recovery-emails
