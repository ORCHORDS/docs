# Event-Driven Fanout Patterns

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A user action (post published, payment confirmed) must trigger
multiple downstream effects: send email, update analytics,
invalidate caches, notify webhooks. Doing this synchronously
in the request path makes the API slow and fragile; one
downstream timeout fails the whole operation.

## Context

Event-driven fanout decouples the producer (the API handler)
from consumers (email, analytics, webhooks). The producer
emits a single event; a broker fans it out to N subscribers
independently. Cloudflare Queues provides at-least-once async
delivery, while Durable Objects provide ordered, stateful
streams for consumers that require sequencing guarantees.

## Pub/Sub vs Point-to-Point

| Model          | Delivery     | Use case                     |
|----------------|--------------|------------------------------|
| Pub/Sub        | One-to-many  | Fanout to N independent jobs |
| Point-to-point | One-to-one   | Work queue, task delegation  |
| Request/Reply  | One-to-one   | RPC over messaging           |

Fanout uses pub/sub. Each consumer subscribes independently;
the broker retains the message until all subscribers ack.
Cloudflare Queues is point-to-point by default; implement
fanout by writing one routing Worker that forwards to N
topic-specific queues.

```typescript
// Routing Worker: fan one event out to N queues
export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body as DomainEvent;
      await env.EMAIL_QUEUE.send(event);
      await env.ANALYTICS_QUEUE.send(event);
      await env.WEBHOOK_QUEUE.send(event);
      msg.ack();
    }
  },
};
```

## At-Least-Once Delivery and Idempotency

Cloudflare Queues guarantees at-least-once delivery: a message
may be delivered more than once if a consumer crashes before
acking. Every consumer must be idempotent.

```typescript
// Idempotent email consumer using D1 dedup table
async function handleEmailEvent(
  event: EmailEvent,
  env: Env,
): Promise<void> {
  const exists = await env.DB.prepare(
    "SELECT 1 FROM sent_events WHERE event_id = ?",
  )
    .bind(event.id)
    .first();
  if (exists) return; // already processed, skip

  await sendEmail(event, env);

  await env.DB.prepare(
    "INSERT INTO sent_events (event_id, processed_at)"
    + " VALUES (?, ?)",
  )
    .bind(event.id, Date.now())
    .run();
}
```

Use a natural idempotency key (event UUID) rather than a
sequence number; sequence numbers depend on ordering that
at-least-once brokers do not provide.

## Durable Objects as Ordered Event Streams

When consumers need strict ordering (audit log, per-entity
state machine), route events through a Durable Object keyed
on the aggregate ID. The DO's single-threaded execution model
serializes concurrent writes automatically.

```typescript
// DO processes events in arrival order per entity
export class EntityStream implements DurableObject {
  constructor(private state: DurableObjectState) {}

  async fetch(req: Request): Promise<Response> {
    const event = await req.json<DomainEvent>();
    const history = await this.state.storage.get<
      DomainEvent[]
    >("history") ?? [];
    history.push(event);
    await this.state.storage.put("history", history);
    return new Response("ok");
  }
}
```

## Back-Pressure and Rate-Limiting Consumers

A slow downstream (e.g. a third-party webhook endpoint) can
cause queue depth to grow unboundedly. Apply back-pressure:

- Set `max_retries` and `visibility_timeout` on the queue so
  slow consumers do not block the partition.
- Use an exponential-backoff retry policy in the consumer
  Worker to avoid hammering a degraded endpoint.
- Emit a metric (`queue_depth`) and alert if it exceeds a
  threshold; this signals consumer throughput is too low.

```toml
# wrangler.toml — consumer Worker binding
[[queues.consumers]]
queue = "webhook-events"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "webhook-dlq"
```

## Dead-Letter Queue Design

Messages that exceed `max_retries` are moved to a DLQ. The
DLQ is itself a Cloudflare Queue. A separate Worker monitors
it and either:

1. Replays the message after operator review, or
2. Records it in a `failed_events` D1 table for alerting.

Always include the original event body, failure reason, and
retry count in the DLQ payload for debuggability.

## Anti-patterns

- Acking a message before the downstream write completes;
  a crash between ack and write loses the event silently.
- Using wall-clock timestamps as idempotency keys; clock
  skew between Workers means collisions are possible.
- Fanning out inside the original HTTP request handler
  instead of enqueueing first; one slow consumer delays
  the user-facing response.
- Building a DLQ without an operator workflow to replay or
  discard messages; the DLQ becomes a black hole.

## Gotchas

- Cloudflare Queues delivers messages in best-effort order,
  not strict FIFO, across a batch. Do not rely on ordering
  within a batch unless using a Durable Object stream.
- Queue consumers must complete within 15 minutes total CPU
  time; long-running consumers must checkpoint progress.
- Sending to a Queue in a `waitUntil` callback is safe but
  errors are swallowed — wrap in try/catch and log.

## Verification

- Write an integration test that publishes an event and
  asserts all downstream D1 rows are created exactly once
  even when the consumer Worker is invoked twice.
- Check DLQ depth via `wrangler queues list` after a
  simulated consumer failure.
- Confirm idempotency key uniqueness constraints in D1 with
  `CREATE UNIQUE INDEX` and assert the INSERT fails on dupe.

## Related

- architecture/at-least-once-delivery.md
- architecture/dead-letter-queue-architecture.md
- architecture/idempotency-design.md
- architecture/outbox-pattern.md
- architecture/backpressure-patterns.md

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/\
consumer-concurrency/
- https://developers.cloudflare.com/durable-objects/\
best-practices/
- https://developers.cloudflare.com/workers/runtime-apis/\
handlers/#queue-handler
