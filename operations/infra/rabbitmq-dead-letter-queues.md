# rabbitmq-dead-letter-queues

**Issue:** Configuring RabbitMQ dead-letter exchanges to capture and reprocess failed messages
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Messages that cannot be processed (due to deserialization errors, business logic rejection, or repeated failures) are either silently discarded or cause infinite retry loops that block the queue. Without a dead-letter strategy, failed messages are invisible.

## Pattern / Solution
Use a dead-letter exchange (DLX) with a separate dead-letter queue (DLQ) per work queue.

**Topology:**
```
Producer → work_exchange → work_queue  (with x-dead-letter-exchange)
                                ↓ (on nack/reject/TTL expiry)
                           dlx_exchange → dlq_queue
```

**Declare with x-arguments (rabbitmq management HTTP API / code):**
```python
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# 1. Declare the dead-letter exchange
channel.exchange_declare(exchange='dlx', exchange_type='direct', durable=True)

# 2. Declare the DLQ
channel.queue_declare(queue='orders.dlq', durable=True)
channel.queue_bind(queue='orders.dlq', exchange='dlx', routing_key='orders')

# 3. Declare the work queue pointing to DLX
channel.queue_declare(
    queue='orders',
    durable=True,
    arguments={
        'x-dead-letter-exchange': 'dlx',
        'x-dead-letter-routing-key': 'orders',
        'x-message-ttl': 60000,   # optional: messages expire after 60 s
        'x-max-length': 10000,    # optional: drop oldest when full
    }
)
```

**Consumer nack with requeue=False to trigger DLX:**
```python
def on_message(ch, method, properties, body):
    try:
        process(body)
        ch.basic_ack(method.delivery_tag)
    except Exception:
        # requeue=False routes to DLX after max retries
        ch.basic_nack(method.delivery_tag, requeue=False)
```

**Retry with backoff using per-message TTL:**
```
Message → work_queue (nack) → dlx → retry_queue (x-message-ttl=30000, x-dead-letter-exchange=work_exchange)
                                                         ↓ (after 30 s TTL)
                                                   re-enters work_queue
```

**Monitor DLQ size:**
```bash
rabbitmqctl list_queues name messages consumers
# Alert when orders.dlq messages > 0 (or > threshold)
```

## Gotchas
- Queue arguments (`x-dead-letter-exchange`) cannot be changed after queue creation; delete and re-declare (requires a maintenance window and message drain).
- `basic_reject` with `requeue=True` does NOT go to the DLX — it goes back to the head of the queue, causing infinite loops.
- Headers on dead-lettered messages include `x-death` with routing history; use this to cap retry attempts in the consumer.
- Quorum queues (recommended for HA) support DLX but do not support `x-max-length-bytes` — use `x-max-length` instead.

## Related
- `kafka-consumer-group-lag.md`
- `prometheus-alertmanager-config.md`
