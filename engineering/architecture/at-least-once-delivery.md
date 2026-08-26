# at-least-once-delivery

**Issue:** Guaranteeing message delivery even under failures, accepting duplicate delivery
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Network failures or broker crashes cause messages to be lost; at-least-once ensures delivery at the cost of possible duplicates.

## Pattern / Solution
Producer retries until it receives an ACK. Consumer may process the same message multiple times.

```
Producer:
  while not acked:
    send(message)
    wait for ACK with timeout
    if timeout: retry (with backoff)

Consumer:
  process(message)
  send ACK  # only after successful processing
  # If crash before ACK: broker redelivers → duplicate processing
```

Kafka example: `enable.idempotence=true` at producer eliminates producer-side duplicates. Consumer-side duplicates still possible.

Design consumers to be idempotent using inbox pattern or natural idempotency (upsert instead of insert).

## Gotchas
- Do not ACK before processing — message loss on crash
- Do not process before ACK — duplicate delivery on crash after processing but before ACK
- Exactly-once is much harder and comes with performance cost

## Related
- `exactly-once-delivery.md`
- `idempotency-design.md`
- `inbox-pattern.md`
