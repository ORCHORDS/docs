# idempotency-keys-for-all-payment-calls

**Issue:** Payment API calls without idempotency keys cause duplicate charges on retries
**Date:** 2026-08-11
**Status:** documented

## What happened
A checkout service retried a Stripe charge after a network timeout. The original charge had succeeded. The retry created a second charge. The customer was billed twice. Stripe's idempotency key feature was documented but not implemented. Refunds and compensation cost more than the engineering time to implement idempotency would have.

## The lesson
Every payment API call (charge, refund, transfer) must include an idempotency key generated from deterministic inputs (e.g., `sha256(user_id + order_id + amount)`). The key prevents duplicate operations if the call is retried due to a network failure, timeout, or crash.

## Why it matters
Network failures are normal. Retries are normal. Without idempotency keys, normal failure handling causes double charges — a financial and trust disaster that is difficult and expensive to remediate.

## How to apply
- [ ] Generate idempotency keys from stable inputs unique to the intent (order ID, not timestamp).
- [ ] Store the idempotency key with the order record before making the payment call.
- [ ] Pass the key in the header or parameter expected by your payment provider.
- [ ] Write a test that calls the payment endpoint twice with the same key and asserts exactly one charge.
- [ ] Apply the same pattern to refunds, subscription updates, and any other payment mutation.

## Related
- `queue-consumers-must-be-idempotent.md`
- `webhook-delivery-is-not-guaranteed.md`
- `eventual-consistency-surprises-clients.md`
