# idempotency-design

**Issue:** Designing operations that can be safely retried without unintended side effects
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Retrying a failed payment charges the customer twice; retrying a failed order creates duplicates.

## Pattern / Solution
An operation is idempotent if performing it multiple times has the same effect as performing it once.

Client-side: include idempotency key in request header.
```
POST /payments
Idempotency-Key: client-generated-uuid-abc123
```

Server-side: check key before processing.
```python
def process_payment(idempotency_key, amount, customer_id):
    if cache.exists(idempotency_key):
        return cache.get(idempotency_key)  # return cached response

    result = charge_card(amount, customer_id)
    cache.set(idempotency_key, result, ttl=24*3600)
    return result
```

HTTP idempotency by method: GET, PUT, DELETE are idempotent by spec; POST is not.

## Gotchas
- Idempotency key TTL must exceed the maximum retry window
- Concurrent requests with the same key need distributed locking or DB unique constraint
- Idempotency is per operation, not per user — scope the key to the specific action

## Related
- `at-least-once-delivery.md`
- `inbox-pattern.md`
- `retry-pattern.md`
