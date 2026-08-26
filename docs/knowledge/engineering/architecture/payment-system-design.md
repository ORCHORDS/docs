# payment-system-design

**Issue:** Payment processing requires strict consistency, auditability, and fault tolerance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A network timeout during a charge request leaves uncertain state since the charge may or may not have been applied at the payment provider.

## Pattern / Solution
Use idempotency keys for all payment API calls. Persist payment intent before calling the provider. Poll for status on timeout rather than retrying blind. Implement double-entry bookkeeping for internal ledgers. Reconcile with the payment provider daily.

## Gotchas
Never trust client-supplied amounts and always recalculate on the server. PCI DSS compliance constrains where card data may be stored or transmitted. Refunds and disputes require separate state machines from the original charge flow.

## Related
idempotency-design, outbox-pattern, exactly-once-delivery
