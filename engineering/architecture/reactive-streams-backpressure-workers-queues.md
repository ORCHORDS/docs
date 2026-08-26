# Reactive Streams and Backpressure: Workers and Queues

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project's moderation pipeline consumes a `PostCreated` Queue and runs each post through an ML
classifier. During a traffic spike the Queue depth can grow from zero to 200,000 messages in
minutes. If the consumer Worker pulls and processes messages as fast as possible without regard
for the downstream classifier's capacity, it overwhelms the classifier, accumulates timeouts,
and triggers mass re-delivery — amplifying the spike rather than absorbing it.

## Context

Cloudflare Queues deliver messages to a consumer Worker in configurable batches. The consumer
acknowledges or retries each message individually. Unlike a streaming protocol with explicit
demand signalling (Reactive Streams `request(n)`), Queues use a push-to-pull hybrid: the
platform delivers batches according to `maxBatchSize` and `maxWaitMs`, and the consumer controls
throughput by how quickly it calls `ack()` or `retry()`. Backpressure is implemented by
adjusting batch size, adding deliberate concurrency limits, and using retry delay to pace
re-delivery.

## Reactive Streams Concepts Mapped to Queues

| Reactive Streams | Cloudflare Queues equivalent |
|------------------|------------------------------|
| Publisher | Queue producer (Worker or external) |
| Subscriber | Consumer Worker (`queue` handler) |
| Subscription / `request(n)` | `maxBatchSize` + `maxWaitMs` in `[[queues]]` binding |
| `onNext` | `msg.body` processing inside the handler |
| `onError` | `msg.retry({ delaySeconds })` |
| `onComplete` | `msg.ack()` |
| Backpressure | Reducing `maxBatchSize`, adding `await` delays, retry with back-off |

## Batch-Sized Demand Control

Set `maxBatchSize` to match the downstream service's sustainable request rate per Worker
invocation. If the classifier handles 10 documents per second and the Worker timeout is 30 s,
cap `maxBatchSize` at 10 * 30 = 300 — but leave headroom for retry overhead.

```toml
# wrangler.toml
[[queues.consumers]]
queue = "post-moderation"
max_batch_size = 25
max_wait_ms = 500
max_retries = 5
dead_letter_queue = "post-moderation-dlq"
```

```typescript
interface Env {
  CLASSIFIER_URL: string; // external ML service
}

interface PostMessage {
  postId: string;
  body: string;
}

export default {
  async queue(
    batch: MessageBatch<PostMessage>,
    env: Env
  ): Promise<void> {
    // Process messages sequentially to honour downstream capacity.
    // Switch to Promise.all with a concurrency limiter (see below) for higher throughput.
    for (const msg of batch.messages) {
      try {
        const result = await classifyPost(env, msg.body);

        if (result.flagged) {
          await flagForReview(env, msg.body.postId);
        }

        msg.ack();
      } catch (err) {
        // Exponential back-off via retry delay — pace re-delivery.
        const attempt = msg.attempts;
        const delaySeconds = Math.min(2 ** attempt, 300); // cap at 5 minutes
        msg.retry({ delaySeconds });
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function classifyPost(
  env: Env,
  msg: PostMessage
): Promise<{ flagged: boolean }> {
  const res = await fetch(env.CLASSIFIER_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: msg.body }),
    signal: AbortSignal.timeout(10_000),
  });

  if (!res.ok) throw new Error(`Classifier ${res.status}`);
  return res.json<{ flagged: boolean }>();
}
```

## Concurrency Limiter for Parallel Processing

When sequential processing is too slow but fully parallel processing overwhelms downstream,
implement a concurrency pool — a semaphore over `Promise.all`.

```typescript
async function withConcurrencyLimit<T>(
  tasks: (() => Promise<T>)[],
  limit: number
): Promise<T[]> {
  const results: T[] = [];
  const executing: Promise<void>[] = [];

  for (const task of tasks) {
    const p = task().then((r) => {
      results.push(r);
    });

    executing.push(p);

    if (executing.length >= limit) {
      await Promise.race(executing);
      // Remove settled promises.
      executing.splice(
        executing.findIndex((e) => {
          let settled = false;
          e.then(() => { settled = true; }).catch(() => { settled = true; });
          return settled;
        }),
        1
      );
    }
  }

  await Promise.all(executing);
  return results;
}

// Consumer using bounded parallelism.
export default {
  async queue(batch: MessageBatch<PostMessage>, env: Env): Promise<void> {
    const CONCURRENCY = 5;

    const tasks = batch.messages.map((msg) => async () => {
      try {
        const result = await classifyPost(env, msg.body);
        if (result.flagged) await flagForReview(env, msg.body.postId);
        msg.ack();
      } catch {
        msg.retry({ delaySeconds: 30 });
      }
    });

    await withConcurrencyLimit(tasks, CONCURRENCY);
  },
} satisfies ExportedHandler<Env>;
```

## Adaptive Backpressure via Queue Depth Sensing

Cloudflare does not expose a native queue depth API to the consumer Worker, but a producer-side
circuit breaker can measure enqueue success rate and back-pressure the producer instead.

```typescript
// Producer Worker: slow down writes when errors exceed threshold.
interface EnqueueMetrics {
  sent: number;
  failed: number;
  windowStart: number;
}

// Module-level metric — acceptable here as it tracks a rate, not mutable entity state.
let metrics: EnqueueMetrics = { sent: 0, failed: 0, windowStart: Date.now() };

async function enqueuePost(env: Env, post: PostMessage): Promise<boolean> {
  const now = Date.now();

  // Reset 10-second window.
  if (now - metrics.windowStart > 10_000) {
    metrics = { sent: 0, failed: 0, windowStart: now };
  }

  // Back-pressure: refuse to enqueue if failure rate > 20 %.
  if (metrics.sent > 50 && metrics.failed / metrics.sent > 0.2) {
    return false; // caller should return 429 or schedule a retry
  }

  try {
    await env.MODERATION.send(post);
    metrics.sent++;
    return true;
  } catch {
    metrics.failed++;
    return false;
  }
}
```

## Dead-Letter Queue and Overflow Handling

Messages that exhaust retries land in the DLQ. A separate low-priority consumer Worker drains
the DLQ on a scheduled basis, re-classifying or archiving posts as needed. This prevents the
hot consumer from becoming a sink for permanently failing messages.

```typescript
// DLQ consumer — runs on a Cron trigger, not a real-time queue consumer.
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // DLQ is also a Queue; consume up to 100 messages per scheduled run.
    // In practice, use a separate queue binding for the DLQ consumer.
    console.log('DLQ drain scheduled — implement batch pull when API stabilises');
  },

  async queue(batch: MessageBatch<PostMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      // Archive to R2 for manual review; do not re-classify to avoid cost spiral.
      await env.ARCHIVE.put(
        `dlq/${msg.id}.json`,
        JSON.stringify({ body: msg.body, timestamp: Date.now() })
      );
      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Setting `maxBatchSize` to 100 without benchmarking the downstream — each message requires an
  outbound fetch; 100 sequential fetches in a single Worker invocation easily exceeds the 30 s
  CPU time limit.
- `msg.retry()` without `delaySeconds` — immediate redelivery under failure hammers the
  downstream and can cause a retry storm.
- Acknowledging a message before the downstream call completes — if the Worker crashes, the
  message is lost; always `ack()` last.
- Using a single Queue for both high-priority (user-facing) and low-priority (batch) work —
  high-priority messages queue behind bulk messages; use separate Queues with separate consumers.

## Gotchas

- Workers have a 128 MB memory limit per invocation; a batch of 100 large messages can exhaust
  it — keep `maxBatchSize` proportional to the per-message payload size.
- `msg.retry({ delaySeconds })` is bounded to the Queue's configured `max_retry_delay`; setting
  300 s in code does not override a lower Queue-level cap.
- The consumer Worker has a wall-clock timeout of 15 minutes for Queue consumers (not the
  standard 30 s CPU limit); use this headroom for slow downstream services.
- For example project's moderation pipeline, ensure the post body is stripped of identifying metadata
  before being sent to an external ML classifier.

## Verification

1. Publish 10,000 messages to the queue with a producer script. Assert consumer throughput does
   not exceed `CONCURRENCY * classifier_rps` by monitoring classifier response times.
2. Inject a classifier error for 25 % of messages. Assert retry delays are non-zero and
   increasing; assert no infinite retry loop (DLQ receives exhausted messages).
3. Set `max_batch_size = 1` and measure end-to-end latency. Gradually increase to 25 and verify
   throughput scales linearly up to the concurrency cap.
4. Kill the consumer Worker mid-batch. Assert no messages are permanently lost after redelivery.

## Related

- [Backpressure Patterns](backpressure-patterns.md)
- [Priority Queue Architecture](priority-queue-architecture.md)
- [Dead-Letter Queue Architecture](dead-letter-queue-architecture.md)
- [Retry Storm Prevention — Workers Jitter Backoff](retry-storm-prevention-workers-jitter-backoff.md)
- [Progressive Retry Topology — Queues Dead Letter Requeue](progressive-retry-topology-queues-dead-letter-requeue.md)
- [Competing Consumers — Queues](competing-consumers-queues.md)

## Sources

- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://developers.cloudflare.com/queues/reference/how-queues-works/
- https://www.reactive-streams.org/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/queues/
