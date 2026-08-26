# event-driven-architecture

**Issue:** When to use event-driven (pub/sub) vs request-response
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a feature: "when a user posts, send a notification
to all their followers." You do it synchronously: the post
endpoint iterates over all followers and calls the
notification service. 10k followers = 10k API calls. The
post endpoint takes 5 seconds. The user waits.

## Root cause
**Synchronous fan-out doesn't scale.** The post endpoint is
on the critical path; the notification delivery is not.

**Source:** Microsoft — Event-driven architecture:
https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/event-driven

> "Event-driven architectures are ... suited for scenarios
> where the producer and consumer are decoupled in time."

## The pattern: producer + consumer + event bus

```ts
// Producer (Pages Function)
async function createPost(request: Request, env: Env): Promise<Response> {
  const post = await savePost(request, env);

  // Publish an event (not a direct call)
  await env.POSTS_EVENTS.send({
    type: 'post.created',
    postId: post.id,
    authorId: post.authorId,
    timestamp: post.createdAt,
  });

  // Return immediately
  return new Response(JSON.stringify({ post }), { status: 201 });
}

// Consumer 1: notifications
async queue(batch, env) {
  for (const msg of batch.messages) {
    if (msg.body.type === 'post.created') {
      const followers = await getFollowers(msg.body.authorId, env);
      for (const followerId of followers) {
        await env.NOTIFICATION_QUEUE.send({
          type: 'notification.send',
          userId: followerId,
          kind: 'new_post',
          postId: msg.body.postId,
        });
      }
      msg.ack();
    }
  }
}

// Consumer 2: search index
async queue(batch, env) {
  for (const msg of batch.messages) {
    if (msg.body.type === 'post.created') {
      await env.SEARCH_INDEX.add({ id: msg.body.postId, ... });
      msg.ack();
    }
  }
}
```

## When to use event-driven

✅ Use event-driven when:
- **The downstream work is async** (notification, indexing,
  analytics)
- **There are multiple consumers** (notification + search +
  analytics all want to know about the event)
- **The producer and consumer scale differently** (1M posts
  but 10M notifications)
- **You need to retry on failure** (queue handles it)

❌ Don't use event-driven when:
- **The user needs the result immediately** (use request-
  response)
- **The downstream is a single service** (use a direct call)
- **The event ordering matters** (queues don't guarantee
  order; use a stream)
- **The event payload is large** (queues have a message size
  limit; use a stream + reference to the data)

## CF Workers event-driven options

### 1. CF Queues (recommended for most)
- Managed queue with at-least-once delivery
- Batch up to 100 messages
- Retry + DLQ
- Free tier: 10M operations/month

```toml
[[queues.producers]]
queue = "events"
binding = "EVENTS"

[[queues.consumers]]
queue = "events"
max_batch_size = 10
max_batch_timeout = 30
```

### 2. Workers Analytics Engine (for analytics)
- High-throughput, low-cardinality
- Best for "I want to count this" not "I want to process this"

```ts
env.ANALYTICS.writeDataPoint({
  blobs: ['post.created', post.authorId],
  doubles: [1],
  indexes: ['post.created'],
});
```

### 3. Service bindings (for direct RPC)
- Synchronous, low-latency
- Not for fan-out

```ts
await env.SEARCH_INDEX.fetch(request);
```

## The "fan-out" problem

For "1 post → 1M notifications," the consumer fans out:
```ts
// Consumer reads the event
async queue(batch, env) {
  for (const msg of batch.messages) {
    const followers = await getFollowers(msg.body.authorId, env);

    // Fan out via another queue
    const notifications = followers.map(f => ({
      type: 'notification.send',
      userId: f.id,
      postId: msg.body.postId,
    }));
    await env.NOTIFICATIONS.sendBatch(notifications);

    msg.ack();
  }
}
```

This pattern (1 producer → 1 consumer that fans out) is
"fan-out on write." It's a trade-off:
- ✅ Producer is fast (single event published)
- ❌ Consumer must handle the fan-out (potential for backpressure)
- ❌ Notification delivery is delayed (not real-time)

For real-time fan-out, use a stream (Kafka, Kinesis).

## The "ordering" problem

Queues don't guarantee order. If you have:
1. User creates a post
2. User edits the post
3. User deletes the post

The notifications might fire in the wrong order. Solutions:
- **Sequence number** in the event (consumer checks)
- **Single-partition queue** (only one consumer instance)
- **Event sourcing** (consumer re-builds state from the
  sequence)

## The "exactly-once" problem

Queues are at-least-once. A message may be delivered twice.
For exactly-once:
- **Idempotent consumer** (check if already processed)
- **Dedup table** (track processed message IDs)

## Verification
- **Test:** `test/event-driven.test.ts > event published,
  consumed, processed` — passes
- **Live:** Queue depth is monitored; alerts on backlog

## Gotchas
- **The event schema is a contract.** Changes break consumers.
  Use schema versioning.
- **The consumer's failure mode matters.** What if the
  consumer crashes? The queue retries. What if the message
  is poison? The DLQ catches it.
- **The event payload should be minimal.** Reference data by
  ID; don't embed the full record. Stale data in the event
  payload is worse than a re-fetch.
- **The producer should not block on the event publish.** A
  failed publish is a problem; either retry, log, or use an
  outbox (write to DB, then a worker reads and publishes).
- **The queue is a SPOF for the consumer.** If the queue is
  down, no work happens. Have a fallback (e.g. cron that
  catches up missed events).

## Related
- `queue-system-design.md`
- `saga-pattern.md` (sagas are event-driven)
- `event-sourcing.md` (related philosophy)
- `idempotency-keys.md` (essential for event consumers)
- CF Queues: https://developers.cloudflare.com/queues/
- CF Analytics: https://developers.cloudflare.com/analytics/
