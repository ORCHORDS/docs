# message-queue-patterns

**Issue:** Choosing and implementing message queue patterns for reliable async communication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Direct service-to-service HTTP calls coupling services together and causing cascade failures. No retry or backpressure mechanism.

## Pattern / Solution
Core patterns:
```
Work Queue (competing consumers):
  Producer → Queue → [Worker A, Worker B, Worker C]
  Use: task distribution, background jobs

Pub/Sub (fan-out):
  Publisher → Topic → [Sub A, Sub B, Sub C]
  Use: event broadcasting, decoupling

Request/Reply (async RPC):
  Requester → Queue → Responder → Reply-Queue → Requester
  Use: async request-response without coupling

Dead Letter Queue (DLQ):
  Queue (maxReceive=3) → DLQ → Alarm → Manual review
  Use: poison message isolation, failure auditing
```

Idempotent consumer (safe to replay):
```python
def process_order(event: dict):
    order_id = event["orderId"]

    # Idempotency check
    if db.exists("SELECT 1 FROM processed_events WHERE event_id = %s", event["eventId"]):
        logger.info(f"Duplicate event {event['eventId']}, skipping")
        return

    with db.transaction():
        fulfill_order(order_id)
        db.execute("INSERT INTO processed_events (event_id, processed_at) VALUES (%s, NOW())",
                   event["eventId"])
```

Outbox pattern (guaranteed delivery with DB writes):
```sql
-- Write to outbox table in same transaction as business data
BEGIN;
  INSERT INTO orders (id, ...) VALUES (...);
  INSERT INTO outbox (aggregate_id, event_type, payload, status)
    VALUES ('order-123', 'ORDER_PLACED', '{"orderId":"order-123"}', 'PENDING');
COMMIT;
-- Separate publisher polls outbox and publishes to queue
```

## Gotchas
- At-least-once delivery is the default for all major queues — design consumers to be idempotent
- Message ordering guarantees differ: Kafka (within partition), SQS FIFO (within message group), SQS standard (no guarantee)
- Large messages (>256 KB SQS, >10 MB Kafka default) need S3/blob storage with pointer pattern
- Dead letter queues need monitoring — messages silently accumulate without alerts

## Related
- `aws-sqs-patterns.md`
- `aws-sns-fanout.md`
- `event-streaming-kafka-vs-kinesis.md`
