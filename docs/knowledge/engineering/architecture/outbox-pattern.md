# outbox-pattern

**Issue:** Reliably publishing events after a DB commit without dual-write problems
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
If you publish to a message broker after DB commit and the broker call fails, events are lost. If before, DB might roll back but event is already sent.

## Pattern / Solution
Write events to an outbox table in the same DB transaction as the business data. A separate relay process publishes them to the broker.

```sql
-- Same transaction:
BEGIN;
  INSERT INTO orders (id, ...) VALUES (...);
  INSERT INTO outbox (id, event_type, payload, published)
    VALUES (gen_uuid(), 'OrderCreated', '{"orderId":...}', false);
COMMIT;

-- Relay process (polling or CDC):
SELECT * FROM outbox WHERE published = false ORDER BY created_at LIMIT 100;
-- For each row: publish to Kafka, then mark published = true
```

CDC alternative: use Debezium to stream outbox table changes via DB log, avoiding polling.

## Gotchas
- Relay must handle broker unavailability with retries — outbox rows accumulate, clean up published rows
- CDC requires DB replication slot; monitor lag
- Ensure idempotent consumers since at-least-once delivery applies

## Related
- `inbox-pattern.md`
- `event-driven-architecture.md`
- `at-least-once-delivery.md`
