# gcp-pub-sub-patterns

**Issue:** Cloud Pub/Sub patterns for reliable message delivery, ordering, and dead-letter handling
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Messages processed out of order, duplicates not handled, no dead-letter queue for poison messages, or push subscriptions timing out.

## Pattern / Solution
```hcl
resource "google_pubsub_topic" "orders" {
  name = "orders"
  message_retention_duration = "86600s"  # 24 h
}

resource "google_pubsub_topic" "orders_dlq" {
  name = "orders-dlq"
}

resource "google_pubsub_subscription" "orders_worker" {
  name  = "orders-worker"
  topic = google_pubsub_topic.orders.id

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"  # 7 days
  retain_acked_messages      = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.orders_dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}
```

Ordered delivery (same ordering key → same subscriber):
```python
publisher = pubsub_v1.PublisherClient()
future = publisher.publish(
    topic_path,
    data=message.encode("utf-8"),
    ordering_key="customer-123"   # same key → ordered delivery
)
```

Enable ordering on the subscription:
```hcl
  enable_message_ordering = true
```

Pull subscriber pattern with exactly-once semantics:
```python
with subscriber.subscribe(subscription_path, callback=callback) as streaming_pull:
    streaming_pull.result(timeout=None)

def callback(message):
    try:
        process(message.data)
        message.ack()
    except Exception:
        message.nack()   # re-deliver after ack_deadline
```

## Gotchas
- Ordering requires the publisher to enable `enable_message_ordering` and use consistent ordering keys
- Pub/Sub delivers at-least-once by default — make consumers idempotent
- DLQ topic needs a subscription to avoid messages expiring unread
- Push subscriptions must return 2xx within ack_deadline — long processing → use pull instead

## Related
- `aws-sqs-patterns.md`
- `event-streaming-kafka-vs-kinesis.md`
- `message-queue-patterns.md`
