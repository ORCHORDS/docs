# exactly-once-delivery

**Issue:** Achieving semantics where a message is processed exactly once end-to-end
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Financial systems need exactly-once: charging a card twice or not at all are both unacceptable.

## Pattern / Solution
True exactly-once delivery does not exist across independent systems. Practically achieved via idempotency + at-least-once.

```
Kafka exactly-once (within Kafka ecosystem):
  - Producer: enable.idempotence=true + transactions
  - Consumer: read_committed isolation
  - Process and produce in a single Kafka transaction

Cross-system (DB + broker):
  - Use outbox pattern: write to DB and outbox atomically
  - Inbox pattern: deduplicate on consumer before DB write
  - Combined: outbox + inbox = effectively-exactly-once
```

The trick: separate "delivery" from "processing". At-least-once delivery + idempotent processing = exactly-once effect.

## Gotchas
- Kafka transactions add 10-20% latency overhead
- Exactly-once only holds within the Kafka cluster; side effects (emails, external APIs) need idempotency
- Cross-datacenter exactly-once is not achievable without significant trade-offs

## Related
- `at-least-once-delivery.md`
- `inbox-pattern.md`
- `outbox-pattern.md`
