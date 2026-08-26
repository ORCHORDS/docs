# dunning-email-sequences

**Issue:** Designing automated email sequences to recover failed subscription payments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe Smart Retries handle the payment retries, but customer communication requires custom email sequences. Dunning emails that communicate urgency and simplify recovery consistently outperform generic failure notices.

## Pattern / Solution
On invoice.payment_failed webhook: Day 0 — send payment failed email with update card link. Day 3 — send action needed with direct link to customer portal. Day 7 — send last chance with a support offer. Day 14 — send access suspended if still unpaid. Link all emails to your Stripe customer portal.

## Gotchas
Do not send more than 3-4 emails — beyond that, customers mark as spam. Personalize subject lines with the amount owed. Stripe's built-in dunning emails can conflict with your custom sequences — disable one or the other.

## Related
stripe-dunning-management, stripe-payment-recovery-emails, stripe-smart-retries, stripe-customer-portal
