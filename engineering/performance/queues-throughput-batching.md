# Cloudflare Queues Throughput Batching

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Queue consumer processes messages one-by-one, triggering a downstream write (D1,
R2, external API) per message. At moderate throughput (hundreds of messages/sec) the per-message
overhead dominates: each consumer invocation opens a connection, executes one small write, then
tears down. Throughput is capped well below the queue's theoretical limit and downstream systems
are hammered with tiny requests.

## Context

Cloudflare Queues delivers messages in configurable batches to a consumer Worker. The consumer
can read up to `max_batch_size` messages per invocation and has up to `max_batch_timeout` seconds
to process them before the batch is considered failed. Optimising throughput means maximising
batch utilisation, fanning out within the batch with `Promise.all`, and writing downstream
resources in bulk rather than row-by-row. Retries, partial failures, and dead-letter routing
must be handled at the batch level.

---

## 1. Configure Maximum Batch Size and Timeout

Set `max_batch_size` as high as downstream constraints allow and give the consumer enough
time to process without false timeouts.

```jsonc
// wrangler.jsonc
{
  "queues": {
    "consumers": [
      {
        "queue": "events-queue",
        "max_batch_size": 100,
        "max_batch_timeout": 30,
        "max_retries": 3,
        "dead_letter_queue": "events-dlq"
      }
    ]
  }
}
```

```typescript
interface Env {
  DB: D1Database;
}

export default {
  async queue(batch: MessageBatch<EventPayload>, env: Env): Promise<void> {
    // batch.messages.length can be up to 100
    await processBatch(batch.messages, env);
    batch.ackAll(); // acknowledge only after successful processing
  },
};
```

## 2. Bulk-write to D1 in a Single Batch

Accumulate INSERT statements and send them as a single `db.batch()` call instead of one
query per message.

```typescript
interface EventPayload {
  userId: string;
  type: string;
  ts: number;
}

async function processBatch(
  messages: readonly Message<EventPayload>[],
  env: Env,
): Promise<void> {
  const insertStmt = env.DB.prepare(
    'INSERT INTO events (user_id, type, ts) VALUES (?1, ?2, ?3)',
  );

  const bound = messages.map(({ body }) =>
    insertStmt.bind(body.userId, body.type, body.ts),
  );

  // One round-trip for the entire batch
  await env.DB.batch(bound);
}
```

## 3. Fan-out Sub-tasks with `Promise.all`

When the batch requires multiple independent downstream operations (e.g., write to D1 and
invalidate a KV cache), run them concurrently within the consumer.

```typescript
async function processWithFanOut(
  messages: readonly Message<EventPayload>[],
  env: Env & { KV: KVNamespace },
): Promise<void> {
  const insertStmt = env.DB.prepare(
    'INSERT INTO events (user_id, type, ts) VALUES (?1, ?2, ?3)',
  );

  const uniqueUsers = [...new Set(messages.map((m) => m.body.userId))];

  await Promise.all([
    // Bulk D1 write
    env.DB.batch(
      messages.map(({ body }) =>
        insertStmt.bind(body.userId, body.type, body.ts),
      ),
    ),
    // Parallel KV invalidation for affected users
    ...uniqueUsers.map((uid) => env.KV.delete(`user:${uid}:event-count`)),
  ]);
}
```

## 4. Partial Acknowledgement on Per-message Failure

When a subset of messages fail, retry only those rather than the whole batch. Use
`message.retry()` and `message.ack()` individually.

```typescript
async function processWithPartialRetry(
  messages: readonly Message<EventPayload>[],
  env: Env,
): Promise<void> {
  const results = await Promise.allSettled(
    messages.map(async (msg) => {
      await writeEvent(msg.body, env);
      return msg;
    }),
  );

  for (let i = 0; i < results.length; i++) {
    const result = results[i];
    if (result.status === 'fulfilled') {
      result.value.ack();
    } else {
      console.error('Message failed, retrying:', messages[i].id, result.reason);
      messages[i].retry({ delaySeconds: 5 });
    }
  }
}
```

## 5. Producer-side Batching with `sendBatch`

On the producer side, coalesce messages before enqueuing to reduce queue overhead and ensure
related events are grouped for the consumer.

```typescript
async function enqueueEvents(
  events: EventPayload[],
  env: Env & { QUEUE: Queue<EventPayload> },
): Promise<void> {
  // sendBatch sends up to 100 messages per call
  const BATCH_LIMIT = 100;
  for (let i = 0; i < events.length; i += BATCH_LIMIT) {
    const chunk = events.slice(i, i + BATCH_LIMIT);
    await env.QUEUE.sendBatch(
      chunk.map((body) => ({ body, contentType: 'json' })),
    );
  }
}
```

---

## Anti-patterns

- **Processing messages one-by-one inside `queue()`** – iterating with sequential `await` in a
  loop means you process at most 1 message per network RTT; use `Promise.all` or batch APIs.
- **`batch.ackAll()` before processing** – acknowledging before the downstream write succeeds
  silently drops messages on write failure with no opportunity for retry.
- **`max_batch_size: 1`** – single-message batches defeat the purpose; the queue overhead per
  invocation dominates useful work.
- **Unbounded concurrency in `Promise.all`** – processing 100 messages each with 3 sub-requests
  can produce 300 concurrent sub-requests, hitting the Workers sub-request limit (1 000 on Paid).
  Chunk if needed.

## Gotchas

- `max_batch_timeout` is a delivery guarantee to the consumer, not a hard processing deadline;
  the Worker's own CPU and wall-clock limits still apply (30 s wall-clock on free, no explicit
  cap on paid for queue consumers as of 2026).
- Messages not explicitly acked or retried within the handler are retried automatically after
  the visibility timeout expires; do not mix `ackAll()` with per-message `retry()`.
- Dead-letter queues require the DLQ to be pre-created and bound in `wrangler.jsonc`;
  messages that exhaust `max_retries` are moved there, not silently dropped.
- `Queue.sendBatch()` accepts a maximum of 100 messages per call; larger sends must be
  chunked at the producer.

## Verification

```typescript
// Emit throughput metrics to Analytics Engine
export default {
  async queue(batch: MessageBatch<EventPayload>, env: Env & { AE: AnalyticsEngineDataset }): Promise<void> {
    const start = Date.now();
    await processBatch(batch.messages, env);
    batch.ackAll();
    env.AE.writeDataPoint({
      blobs: ['queue_consumer'],
      doubles: [batch.messages.length, Date.now() - start],
    });
  },
};
```

Monitor `messages_per_invocation` (target ≥ 80 % of `max_batch_size` under load) and
`ms_per_message` (target < 5 ms for simple DB writes). Alert if `ms_per_message` > 50 ms.

## Related

- `workers-queues-background-offload.md`
- `d1-batch-query-performance-optimization.md`
- `workers-subrequest-fanout-parallelism.md`

## Sources

- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://developers.cloudflare.com/queues/reference/javascript-apis/
- https://developers.cloudflare.com/queues/best-practices/
