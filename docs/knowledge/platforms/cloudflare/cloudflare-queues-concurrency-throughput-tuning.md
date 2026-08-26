# Cloudflare Queues Consumer Concurrency and Batch-Size Throughput Tuning

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Queues consumer Worker processes messages too slowly, causing the queue depth
to grow unboundedly during traffic spikes. Alternatively, the consumer is saturating
downstream services (a D1 database, an external API) because Cloudflare dispatches too
many concurrent Worker invocations. The team needs deterministic control over throughput,
concurrency, and back-pressure.

## Context

Cloudflare Queues delivers messages in batches to a consumer Worker. The platform controls
how many concurrent consumer invocations run in parallel (`max_concurrency`) and how many
messages each invocation receives (`max_batch_size`). Throughput is approximately:

```
effective_tps ≈ max_concurrency × max_batch_size / avg_processing_time_seconds
```

Default settings are conservative (`max_concurrency = 2`, `max_batch_size = 10`), which
is appropriate for low-volume queues but creates bottlenecks at scale.

---

## Wrangler Configuration

```toml
# wrangler.toml
[[queues.consumers]]
queue = "my-work-queue"
max_batch_size      = 100   # messages per Worker invocation (max: 100)
max_batch_timeout   = 5     # seconds to wait before dispatching a partial batch
max_retries         = 3     # per-message retry limit before DLQ
dead_letter_queue   = "my-work-queue-dlq"
max_concurrency     = 20    # parallel Worker invocations (max: 20 on paid plan)
retry_delay         = 10    # seconds before first retry (exponential back-off applied)
visibility_timeout  = 60    # seconds; must exceed expected processing time
```

Key interactions:
- `max_batch_timeout` only matters when the queue drains below `max_batch_size`; during
  sustained load, batches fill immediately.
- `visibility_timeout` must be longer than `max_batch_timeout` + expected processing time
  or messages re-appear before the consumer acks them.

---

## Consumer Worker with Parallel Batch Processing

The default sequential loop wastes most of the batch timeout waiting on I/O. Use
`Promise.allSettled` to parallelize within the batch:

```ts
import type { Queue, MessageBatch, Message } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  OUTPUT_QUEUE: Queue<ProcessedEvent>;
}

type WorkItem = { userId: string; eventType: string; payload: unknown };

export default {
  async queue(batch: MessageBatch<WorkItem>, env: Env): Promise<void> {
    // Process all messages in the batch concurrently
    const results = await Promise.allSettled(
      batch.messages.map((msg) => processMessage(msg, env))
    );

    // Selectively ack/retry based on outcome
    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      const msg = batch.messages[i];
      if (result.status === 'fulfilled') {
        msg.ack();
      } else {
        const retryable = result.reason?.retryable !== false;
        if (retryable) {
          msg.retry({ delaySeconds: 30 });
        } else {
          // Ack to prevent infinite retry; log to dead-letter analysis
          console.error('Poison message', msg.id, result.reason);
          msg.ack();
        }
      }
    }
  },
};

async function processMessage(
  msg: Message<WorkItem>,
  env: Env
): Promise<void> {
  const { userId, eventType, payload } = msg.body;
  await env.DB.prepare(
    'INSERT INTO events (user_id, type, payload, processed_at) VALUES (?, ?, ?, ?)'
  )
    .bind(userId, eventType, JSON.stringify(payload), Date.now())
    .run();
}
```

---

## Back-pressure: Rate-Limiting Downstream Services

When the downstream (e.g. a third-party API with 100 req/s limit) cannot absorb full
concurrency, use a semaphore within the batch:

```ts
class Semaphore {
  private permits: number;
  private queue: Array<() => void> = [];

  constructor(permits: number) {
    this.permits = permits;
  }

  acquire(): Promise<void> {
    if (this.permits > 0) {
      this.permits--;
      return Promise.resolve();
    }
    return new Promise((resolve) => this.queue.push(resolve));
  }

  release(): void {
    const next = this.queue.shift();
    if (next) next();
    else this.permits++;
  }
}

export default {
  async queue(batch: MessageBatch<WorkItem>, env: Env): Promise<void> {
    // Allow at most 5 concurrent API calls within this invocation
    const sem = new Semaphore(5);

    await Promise.allSettled(
      batch.messages.map(async (msg) => {
        await sem.acquire();
        try {
          await callExternalAPI(msg.body);
          msg.ack();
        } catch {
          msg.retry();
        } finally {
          sem.release();
        }
      })
    );
  },
};
```

---

## Tuning Strategy by Workload Type

| Workload | `max_batch_size` | `max_concurrency` | Notes |
|---|---|---|---|
| D1 batch writes | 100 | 5–10 | D1 has 1000 req/s limit per DB; batch insert reduces round-trips |
| External API (rate-limited) | 25 | 2–4 | Multiply: 25 × 4 = 100 req/batch dispatch |
| CPU-heavy (image processing) | 5–10 | 10–20 | CPU time limit 30 s; small batches prevent timeouts |
| Fan-out (send to multiple queues) | 100 | 20 | Pure Cloudflare I/O; maximize both dimensions |
| Idempotent R2 writes | 50 | 10 | R2 is high-concurrency safe; no external rate limit |

---

## Monitoring Queue Depth and Consumer Lag

```bash
# Via Cloudflare API — queue metrics (rolling 5-minute window)
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/queues/${QUEUE_ID}/metrics" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '{depth: .result.current_depth, consumers: .result.consumers}'
```

Emit consumer lag as an Analytics Engine data point for alerting:

```ts
export default {
  async queue(batch: MessageBatch<WorkItem>, env: Env): Promise<void> {
    const start = Date.now();
    // ... process messages ...
    const elapsed = Date.now() - start;

    env.AE.writeDataPoint({
      blobs: ['queue-consumer'],
      doubles: [batch.messages.length, elapsed, Date.now() - batch.messages[0].timestamp],
    });
  },
};
```

---

## Anti-patterns

- Using `batch.ackAll()` before processing completes — if the Worker throws mid-batch,
  successfully ack'd messages are lost permanently.
- Setting `max_concurrency` to 20 against a D1 database with `max_batch_size = 100` —
  20 × 100 = 2000 concurrent D1 statements will exceed D1's per-database concurrency
  and return `SQLITE_BUSY`.
- Setting `visibility_timeout` lower than `max_batch_timeout` — messages become visible
  again before the consumer even starts processing.
- Ignoring `retry_delay` — without it, a poison message that always fails hits `max_retries`
  in seconds, flooding the DLQ and consuming retry quota.

---

## Gotchas

- `max_concurrency` is a ceiling, not a guarantee; Cloudflare may dispatch fewer
  invocations during cold starts or regional capacity constraints.
- Messages delivered across multiple batches in a single second may share a timestamp;
  do not use `msg.timestamp` as a strict ordering key.
- `msg.retry({ delaySeconds: N })` overrides `retry_delay` in `wrangler.toml` for that
  specific message only.
- The 30-second CPU time limit applies per Worker invocation; a batch of 100 slow messages
  can hit the limit. Prefer smaller `max_batch_size` for CPU-heavy tasks.
- Queues are at-least-once; always design consumers to be idempotent using a dedup key
  stored in D1 or KV.

---

## Verification

```bash
# Watch queue depth before and after tuning
watch -n 5 'curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/queues/${QUEUE_ID}/metrics" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq ".result.current_depth"'

# Confirm DLQ is not growing
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/queues/${DLQ_ID}/metrics" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.current_depth'
```

---

## Related

- `queues-batch-processing.md`
- `queues-dlq-patterns.md`
- `cloudflare-queues-dead-letter-dlq.md`
- `cloudflare-queues-delayed-delivery-scheduling.md`
- `workers-resource-limits.md`

---

## Sources

- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- https://developers.cloudflare.com/queues/reference/configuration/
- https://developers.cloudflare.com/queues/examples/batch-processing/
