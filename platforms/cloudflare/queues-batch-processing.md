# queues-batch-processing

**Issue:** Efficient batch processing patterns for Cloudflare Queues consumers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Queues delivers messages in batches to the consumer Worker. Processing each message individually (one DB write per message) is inefficient. Batching DB writes, HTTP calls, and acknowledging in bulk is essential for throughput.

## Pattern / Solution

```toml
# wrangler.toml — tune batch parameters
[[queues.consumers]]
queue = "events"
max_batch_size = 100        # up to 100 messages per batch
max_batch_timeout = 10      # wait up to 10s to fill the batch
max_concurrency = 5         # up to 5 concurrent consumer invocations
max_retries = 3
retry_delay = 30
```

```typescript
interface EventPayload {
  userId: string;
  action: string;
  timestamp: number;
  metadata: Record<string, string>;
}

export default {
  async queue(batch: MessageBatch<EventPayload>, env: Env): Promise<void> {
    const succeeded: Message<EventPayload>[] = [];
    const failed: Message<EventPayload>[] = [];

    // 1. Validate all messages first
    for (const message of batch.messages) {
      if (!message.body.userId || !message.body.action) {
        failed.push(message);
      } else {
        succeeded.push(message);
      }
    }

    // 2. Bulk insert to D1 in a single transaction
    if (succeeded.length > 0) {
      try {
        await env.DB.batch(
          succeeded.map(msg =>
            env.DB.prepare(
              `INSERT INTO events (user_id, action, ts, meta) VALUES (?, ?, ?, ?)`
            ).bind(
              msg.body.userId,
              msg.body.action,
              msg.body.timestamp,
              JSON.stringify(msg.body.metadata)
            )
          )
        );

        // Ack all succeeded messages at once
        batch.ackAll();  // alternative to individual message.ack()
      } catch (err) {
        console.error('Batch insert failed:', err);
        // Retry individual messages — exponential backoff
        for (const msg of succeeded) {
          msg.retry({ delaySeconds: 30 });
        }
      }
    }

    // 3. Retry invalid messages with max delay (they'll hit DLQ after max_retries)
    for (const msg of failed) {
      msg.retry({ delaySeconds: 300 });
    }
  },
};
```

**Parallel processing with concurrency control:**
```typescript
async function processBatchConcurrently<T>(
  messages: Message<T>[],
  handler: (msg: Message<T>) => Promise<void>,
  concurrency = 10
): Promise<void> {
  for (let i = 0; i < messages.length; i += concurrency) {
    const chunk = messages.slice(i, i + concurrency);
    await Promise.allSettled(chunk.map(async (msg) => {
      try {
        await handler(msg);
        msg.ack();
      } catch {
        msg.retry();
      }
    }));
  }
}
```

## Gotchas
- `batch.ackAll()` acks **all** messages in the batch, including any you intended to retry — call it only after all processing succeeds.
- `batch.retryAll()` retries all messages; useful when a downstream dependency is down.
- Each consumer invocation has a **15-minute** CPU/wall-clock limit; large batches that do slow work may time out.
- `max_batch_size` is a maximum, not a guarantee — batches may be smaller, especially at low traffic.
- Messages in the same batch are **not** guaranteed to be in order of insertion.
- If the consumer Worker throws (unhandled exception), all messages in the batch are automatically retried.
- `max_concurrency` limits simultaneous isolates; increasing it improves throughput but uses more compute.

## Related
- `workers-workers-queues-patterns.md`
- `queues-dlq-patterns.md`
- `d1-best-practices.md`
