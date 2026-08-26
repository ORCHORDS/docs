# chargeback-response-process

**Issue:** Responding to payment disputes with evidence to win chargebacks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe sends email notifications for disputes. You have 7-21 days to respond with evidence. Without a response, you automatically lose.

## Pattern / Solution
Respond via Stripe Dashboard or API. Submit evidence: customer name, email, IP address, purchase description, terms of service accepted with timestamp, prior communication. For SaaS, include login logs showing the customer used the service.

## Gotchas
Digital goods disputes are harder to win because there is no physical delivery proof. For subscription disputes claiming not authorized, show the signup IP, date, and email confirmation. Card networks have final say — even strong evidence does not guarantee a win.

## Related
chargeback-prevention, stripe-radar-fraud-rules, payment-audit-logging
