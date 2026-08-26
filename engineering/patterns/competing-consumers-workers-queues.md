# Competing Consumers: Parallel Queue Processing with Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A single queue consumer Worker is a bottleneck. Jobs pile up because each message requires significant CPU time (image resizing, LLM calls, PDF generation, webhook delivery). You need to scale out consumers horizontally without messages being processed twice.

Classic signs:
- Queue depth grows faster than it drains
- P99 message latency measured in minutes, not seconds
- CPU limit (30 s for paid Workers) hit per message
- You want N parallel consumers without managing servers

---

## Context

The Competing Consumers pattern deploys multiple identical consumer Workers. The message broker (Cloudflare Queues) guarantees **at-least-once delivery with exclusive lease**: a message is handed to exactly one consumer at a time. If that consumer fails or times out, the queue re-delivers to another. Consumers race to process distinct messages—they never see the same message simultaneously.

Cloudflare Queues handles the broker side automatically. Scaling is controlled via `max_concurrency` in `wrangler.toml` and the queue's batch settings.

```
Queue
 ├─ message A → Worker instance 1
 ├─ message B → Worker instance 2
 ├─ message C → Worker instance 3
 └─ message D → Worker instance 1 (after A completes)
```

---

## `wrangler.toml` Configuration

```toml
[[queues.producers]]
queue = "jobs"
binding = "JOB_QUEUE"

[[queues.consumers]]
queue = "jobs"
max_batch_size = 10          # messages per batch per instance
max_batch_timeout = 2        # wait up to 2 s to fill a batch
max_retries = 4
dead_letter_queue = "jobs-dlq"
max_concurrency = 20         # up to 20 simultaneous consumer instances
visibility_timeout_ms = 60000  # 60 s lease per batch
```

---

## Message Producer

```typescript
// src/producer.ts
export interface Env {
  JOB_QUEUE: Queue<Job>;
}

interface Job {
  id: string;
  type: "resize-image" | "send-email" | "generate-pdf";
  payload: unknown;
  enqueuedAt: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<Omit<Job, "id" | "enqueuedAt">>();

    const job: Job = {
      id: crypto.randomUUID(),
      enqueuedAt: Date.now(),
      ...body,
    };

    await env.JOB_QUEUE.send(job, {
      contentType: "json",
    });

    return Response.json({ jobId: job.id, queued: true }, { status: 202 });
  },
};
```

---

## Idempotent Consumer Worker

Each consumer instance processes an exclusive batch. Because Queues guarantee at-least-once delivery, the handler **must be idempotent**—processing the same message twice should produce the same outcome.

```typescript
// src/consumer.ts
export interface Env {
  DB: D1Database;
  JOB_QUEUE: Queue<Job>;
}

export default {
  async queue(batch: MessageBatch<Job>, env: Env): Promise<void> {
    const results = await Promise.allSettled(
      batch.messages.map((msg) => processJob(msg.body, env))
    );

    for (let i = 0; i < batch.messages.length; i++) {
      const result = results[i];
      const msg = batch.messages[i];

      if (result.status === "fulfilled") {
        msg.ack(); // release the lease, message is done
      } else {
        console.error(`job ${msg.body.id} failed:`, result.reason);
        msg.retry({ delaySeconds: exponentialDelay(msg.attempts) });
      }
    }
  },
};

function exponentialDelay(attempt: number): number {
  // 2s, 4s, 8s, 16s caps at 60 s
  return Math.min(2 ** attempt * 2, 60);
}

async function processJob(job: Job, env: Env): Promise<void> {
  // Guard against duplicate delivery using D1 as a processed-set
  const existing = await env.DB.prepare(
    "SELECT id FROM processed_jobs WHERE id = ?"
  )
    .bind(job.id)
    .first();

  if (existing) {
    console.log(`job ${job.id} already processed, skipping`);
    return; // idempotent skip
  }

  // Do the real work
  switch (job.type) {
    case "resize-image":
      await handleImageResize(job.payload);
      break;
    case "send-email":
      await handleEmail(job.payload);
      break;
    case "generate-pdf":
      await handlePdfGeneration(job.payload);
      break;
    default:
      throw new Error(`Unknown job type: ${(job as Job).type}`);
  }

  // Mark processed atomically
  await env.DB.prepare(
    "INSERT OR IGNORE INTO processed_jobs (id, processed_at) VALUES (?, ?)"
  )
    .bind(job.id, new Date().toISOString())
    .run();
}

// Stub implementations
async function handleImageResize(_payload: unknown): Promise<void> {}
async function handleEmail(_payload: unknown): Promise<void> {}
async function handlePdfGeneration(_payload: unknown): Promise<void> {}
```

---

## Observing Consumer Health via DLQ

```typescript
// src/dlq-monitor.ts
export default {
  async queue(batch: MessageBatch<Job>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      console.error(JSON.stringify({
        level: "error",
        event: "job_permanently_failed",
        jobId: msg.body.id,
        type: msg.body.type,
        enqueuedAt: msg.body.enqueuedAt,
        age_ms: Date.now() - msg.body.enqueuedAt,
      }));

      // Persist for ops review or manual retry
      await env.DB.prepare(
        `INSERT OR IGNORE INTO failed_jobs (id, type, payload, failed_at)
         VALUES (?, ?, ?, ?)`
      )
        .bind(
          msg.body.id,
          msg.body.type,
          JSON.stringify(msg.body.payload),
          new Date().toISOString()
        )
        .run();

      msg.ack(); // Remove from DLQ after storing
    }
  },
};
```

---

## Anti-patterns

- **Sharing mutable state between consumer instances via KV**: KV is eventually consistent; two instances updating the same counter simultaneously will silently drop increments. Use Durable Objects for shared counters.
- **Not implementing idempotency**: Queues guarantee at-least-once. Without a processed-set check, transient failures cause duplicate side-effects (double emails, double charges).
- **Ignoring per-message `ack()` / `retry()`**: Calling `batch.ackAll()` is convenient but hides failures. Ack each message individually so failed ones retry independently.
- **Setting `max_concurrency` to 1 to avoid races**: This defeats the purpose. Fix the race condition (use Durable Objects or D1 transactions) rather than serialising globally.
- **Long-running CPU work without sub-batching**: The Worker CPU limit is 30 s. If a single job exceeds this, break it into stages using a second queue or R2 intermediate storage.

---

## Gotchas

- `max_concurrency` controls simultaneous consumer *invocations*, not messages. With `max_batch_size = 10` and `max_concurrency = 20`, up to 200 messages can be in-flight simultaneously.
- The visibility timeout (`visibility_timeout_ms`) must be longer than your worst-case job processing time. If a job exceeds the timeout, the queue re-delivers the message to another instance while the original is still running—causing duplicates.
- Consumer Workers run in a **separate script** from the producer. They share bindings defined in `wrangler.toml` but cannot share module-level state.
- Retried messages retain their original `id`. Your idempotency check must use the job's own `id`, not any database auto-increment.
- D1 has a 10 ms CPU time limit per read in the free tier and 30 ms in paid; batch your `processed_jobs` lookups when possible.

---

## Verification

1. Enqueue 100 jobs via the producer and watch queue depth in the Cloudflare dashboard drain in parallel.
2. Force a consumer to throw an error for job IDs ending in `0` and confirm those messages appear in the DLQ after `max_retries`.
3. Send the same job ID twice; confirm D1's `processed_jobs` table has one row and the action ran once.
4. Set `max_concurrency = 1` temporarily and time throughput; increase to 10 and confirm near-linear throughput scaling.
5. Check Cloudflare Logpush or `wrangler tail` for `job_permanently_failed` events after DLQ delivery.

---

## Related

- `dead-letter-queue-pattern.md` — handling permanently failed messages
- `fan-out-queues-workers.md` — one producer, many consumer types
- `priority-queue-workers-queues.md` — ordering work by urgency
- `idempotency-key-pattern-workers-d1.md` — safe retries at the application layer
- `exponential-backoff-jitter-workers.md` — retry delay strategies

---

## Sources

- Cloudflare Queues consumer configuration: https://developers.cloudflare.com/queues/configuration/configure-queues/
- Cloudflare Queues JavaScript API: https://developers.cloudflare.com/queues/javascript-apis/
- Enterprise Integration Patterns — Competing Consumers: https://www.enterpriseintegrationpatterns.com/CompetingConsumers.html
