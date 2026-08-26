# payment-audit-logging

**Issue:** Logging payment events for security auditing, dispute evidence, and compliance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Payment disputes and fraud investigations require a complete audit trail: who initiated a charge, from which IP, with what payment method, and what the response was.

## Pattern / Solution
Log every payment API call with: timestamp, user_id, session_id, IP address, payment_method_id, amount, currency, stripe_request_id, response_status. Store in an append-only log. Index by user_id, payment_intent_id, and timestamp. Retain for 7 years.

## Gotchas
Never log full card numbers or CVV — only log last4 and card fingerprint. Treat payment logs as sensitive data — restrict access to finance and security teams. Stripe Sigma provides their logs; your logs should cover the application layer that Sigma cannot see.

## Related
chargeback-response-process, payment-data-retention, payment-reconciliation, pci-dss-scope-reduction
