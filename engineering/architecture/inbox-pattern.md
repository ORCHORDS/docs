# inbox-pattern

**Issue:** Deduplicating incoming messages on the consumer side to achieve exactly-once processing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
At-least-once delivery means consumers receive duplicate messages; processing them twice causes data corruption.

## Pattern / Solution
Consumer stores a record of processed message IDs before (or atomically with) processing.

```sql
-- Consumer receives message with id = "evt-abc123"
BEGIN;
  -- Check if already processed
  SELECT 1 FROM inbox WHERE message_id = 'evt-abc123';
  -- If exists: skip. If not:
  INSERT INTO inbox (message_id, processed_at) VALUES ('evt-abc123', now());
  -- Process the message (business logic)
  UPDATE inventory SET stock = stock - 1 WHERE ...;
COMMIT;
```

The inbox check + business operation must be atomic (same transaction) to avoid TOCTOU race.

## Gotchas
- Inbox table grows unboundedly; archive or TTL old records
- Idempotency key must be stable across retries — use the message broker's message ID
- Unique constraint on message_id is your safety net; handle unique violation as "already processed"

## Related
- `outbox-pattern.md`
- `idempotency-design.md`
- `exactly-once-delivery.md`
