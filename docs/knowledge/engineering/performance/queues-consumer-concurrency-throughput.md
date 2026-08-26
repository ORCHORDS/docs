# Workers Queues Consumer Concurrency — Throughput Tuning

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Workers Queue processes webhook deliveries or async job payloads, but throughput
plateaus at ~50 messages/s despite the producer saturating the queue. The consumer
Worker spends most of its time awaiting downstream HTTP calls (outbound webhooks,
D1 writes, R2 uploads). CPU utilisation per invocation is low (< 20 ms CPU / message)
but wall-clock time is high (200–600 ms per message). Increasing the batch size alone
does not help because the bottleneck is I/O concurrency within each batch.

## Context

Workers Queues delivers batches of messages to a consumer Worker. The consumer's
`queue` handler receives the entire batch and can process messages sequentially or in
parallel. By default, developers write sequential loops; each message's async I/O
blocks the next, serialising what should be concurrent work. The correct pattern is
to fan out all messages in a batch with `Promise.all()` or `Promise.allSettled()`,
then `ack` or `retry` individually based on outcome. Combined with `max_batch_size`
and `max_concurrency` settings in `wrangler.toml`, this maximises messages-per-second
without exceeding downstream rate limits.

## Setting Consumer Concurrency in `wrangler.toml`

```toml
[[queues.consumers]]
queue = "webhook-delivery"
max_batch_size    = 100   # messages per batch
max_batch_timeout = 5     # seconds to wait before delivering a partial batch
max_retries       = 3
dead_letter_queue = "webhook-dlq"
# max_concurrency controls parallel consumer Worker invocations
# Cloudflare scales this automatically; set it to cap downstream pressure
max_concurrency   = 10
```

## Naive Sequential Pattern (Baseline — Slow)

```typescript
export default {
  async queue(batch: MessageBatch<WebhookJob>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await deliverWebhook(message.body, env); // awaits each in series
        message.ack();
      } catch {
        message.retry({ delaySeconds: 30 });
      }
    }
  },
};
```

With 100-message batches and 300 ms per webhook, this takes 30 s — hitting the 30 s
wall-clock cap. Only ~3 msg/s effective throughput.

## Fan-Out Pattern — Process Entire Batch Concurrently

```typescript
export default {
  async queue(batch: MessageBatch<WebhookJob>, env: Env): Promise<void> {
    const tasks = batch.messages.map(async (message) => {
      try {
        await deliverWebhook(message.body, env);
        message.ack();
      } catch (err) {
        console.error('delivery failed', message.id, err);
        message.retry({ delaySeconds: 30 });
      }
    });

    // allSettled ensures we ack/retry ALL messages even if some throw
    await Promise.allSettled(tasks);
  },
};
```

With 100-message batches, 300 ms per webhook, and 100-way concurrency: ~300 ms total
→ ~333 msg/s from a single consumer invocation.

## Bounded Concurrency for Rate-Limited Upstreams

When the downstream webhook endpoint enforces a rate limit (e.g., 20 req/s), a full
100-way fan-out causes 429 errors. Use a concurrency limiter.

```typescript
async function withConcurrencyLimit<T>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<void>,
): Promise<void> {
  const queue = [...items];
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (queue.length > 0) {
      const item = queue.shift()!;
      await fn(item);
    }
  });
  await Promise.all(workers);
}

export default {
  async queue(batch: MessageBatch<WebhookJob>, env: Env): Promise<void> {
    const messages = [...batch.messages];

    await withConcurrencyLimit(messages, 20, async (message) => {
      try {
        await deliverWebhook(message.body, env);
        message.ack();
      } catch {
        message.retry({ delaySeconds: 60 });
      }
    });
  },
};
```

## Tiered Retry with Exponential Backoff via `delaySeconds`

```typescript
function retryDelay(attempt: number): number {
  // 30 s, 90 s, 270 s caps at 3 retries (wrangler.toml max_retries = 3)
  return Math.min(30 * 3 ** attempt, 600);
}

export default {
  async queue(batch: MessageBatch<WebhookJobWithAttempt>, env: Env): Promise<void> {
    await Promise.allSettled(
      batch.messages.map(async (message) => {
        const { attempt = 0, ...job } = message.body;
        try {
          await deliverWebhook(job, env);
          message.ack();
        } catch (err) {
          const delay = retryDelay(attempt);
          console.warn(`retry attempt=${attempt} delay=${delay}s`, err);
          message.retry({ delaySeconds: delay });
        }
      }),
    );
  },
};
```

## Dead-Letter Queue Monitoring

```typescript
// DLQ consumer: log failures to Analytics Engine for alerting
export default {
  async queue(
    batch: MessageBatch<WebhookJob>,
    env: Env & { ANALYTICS: AnalyticsEngineDataset },
  ): Promise<void> {
    for (const message of batch.messages) {
      env.ANALYTICS.writeDataPoint({
        blobs: [message.body.url, message.body.event],
        doubles: [Date.now()],
        indexes: ['webhook_dlq'],
      });
      message.ack(); // drain DLQ after logging
    }
  },
};
```

## Anti-patterns

- **`batch.retryAll()` on any individual failure** — retries the entire batch,
  including already-succeeded messages; always `ack` and `retry` per message.
- **`await`ing each message in a `for` loop** — serialises I/O; use `Promise.allSettled`.
- **Setting `max_batch_size = 1`** — eliminates batching benefits; use 10–100.
- **No DLQ configured** — messages that exhaust retries are silently dropped without
  a dead-letter queue.
- **Unbounded fan-out against rate-limited APIs** — all messages fail with 429;
  use the concurrency limiter pattern above.

## Gotchas

- `message.ack()` and `message.retry()` are fire-and-forget calls; they do not
  return Promises. Do not `await` them.
- The 30 s wall-clock limit applies to the entire batch handler. With large batches
  and slow upstreams, bounded concurrency + lower `max_batch_size` is safer than
  unbounded fan-out.
- `max_concurrency` in `wrangler.toml` limits *parallel Worker invocations*, not
  parallelism within a single invocation. Both levers are needed.
- Retried messages with `delaySeconds` re-enter the queue tail; they are not
  prioritised. Under sustained failure the queue depth grows; set alerts on
  `queues_messages_delayed` metric.

## Verification

```bash
# Check queue depth and consumer throughput in Cloudflare dashboard
# Workers > Queues > webhook-delivery > Metrics

# Tail consumer Worker for ack/retry rates
wrangler tail webhook-consumer --format=json | \
  jq '.logs[] | select(.message | test("ack|retry"))'

# Measure effective throughput: messages acked / wall-clock time
wrangler tail webhook-consumer --format=json | \
  jq -s '{acked: map(select(.logs[].message=="ack")) | length, duration_s: (last.timestamp - first.timestamp) / 1000}'
```

## Related

- `queues-throughput-batching.md` — producer-side batching strategies
- `queues-consumer-backpressure-flow-control.md` — flow control under load
- `workers-subrequest-fanout-parallelism.md` — parallel fetch patterns in Workers
- `workers-waituntil-background-processing.md` — background work after response

## Sources

- Cloudflare Queues Docs: https://developers.cloudflare.com/queues/
- Queues consumer configuration: https://developers.cloudflare.com/queues/configuration/configure-queues/
- Cloudflare Blog: "Announcing Cloudflare Queues" (2023)
