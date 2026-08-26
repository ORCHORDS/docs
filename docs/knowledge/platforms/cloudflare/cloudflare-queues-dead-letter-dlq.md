# Cloudflare Queues — Consumer Retry Policy, DLQ Routing & Poison-Message Detection

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) uses Queues for audio-processing background jobs (transcode requests, waveform generation). Jobs occasionally fail permanently — bad uploads, codec errors — and re-queuing them forever exhausts retry budgets and masks real failures. Mobile clients that trigger jobs on poor networks produce duplicate enqueues. The team needs a dead-letter queue (DLQ) pattern, poison-message detection, and reliable delivery guarantees tuned for mobile-triggered traffic.

## Context

Cloudflare Queues uses a push-based consumer model: messages are delivered to a Worker consumer in batches. Each batch has a visibility timeout; if the consumer does not acknowledge (via `message.ack()` / `batch.ackAll()`) within the timeout, all unacknowledged messages are re-queued. There is no native DLQ feature with a single config line — DLQ routing is implemented in application code by explicitly routing failed messages to a second queue after exhausting retries.

example project architecture:

```
mobile client
    |
    v
Workers API (/api/transcode)
    |  enqueue
    v
example project-jobs-queue  (primary queue)
    |  consumer (Worker: job-consumer)
    v
D1: jobs table (tracks attempt counts)
    |
    +-- success --> R2: processed audio
    |
    +-- permanent fail --> example project-dlq-queue (DLQ)
                              |
                              v
                          DLQ consumer Worker
                          (alerts + stores to D1 dlq_events table)
```

## Queue and DLQ Configuration

`wrangler.toml`:

```toml
[[queues.producers]]
queue = "example project-jobs-queue"
binding = "JOBS_QUEUE"

[[queues.producers]]
queue = "example project-dlq-queue"
binding = "DLQ_QUEUE"

[[queues.consumers]]
queue = "example project-jobs-queue"
max_batch_size = 10
max_batch_timeout = 30   # seconds: wait up to 30s to fill a batch
max_retries = 3          # Cloudflare will retry up to 3 times before considering dead
dead_letter_queue = "example project-dlq-queue"  # native DLQ: after max_retries, CF routes here
```

With `dead_letter_queue` set, Cloudflare's queue service automatically routes messages that exhaust `max_retries` to the named DLQ — no application code needed for the final routing step. The DLQ must exist as a queue in the account.

Create the queues:

```bash
wrangler queues create example project-jobs-queue
wrangler queues create example project-dlq-queue
```

## Retry Policy Deep Dive

| Setting | Type | Effect |
|---|---|---|
| `max_retries` | integer (0-100) | Max delivery attempts per message before DLQ |
| `max_batch_size` | integer (1-100) | Max messages per consumer invocation |
| `max_batch_timeout` | integer (0-30) | Max seconds to wait before delivering partial batch |
| `retry_delay` | integer (seconds) | Delay before retry (set per-message in consumer) |
| Visibility timeout | ~30s (fixed) | Time consumer has to ack before re-queue |

Per-message retry delay (set in the consumer, not wrangler.toml):

```typescript
export default {
  async queue(batch: MessageBatch<JobMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const result = await processJob(message.body, env);
      if (result.success) {
        message.ack();
      } else if (result.retryable) {
        // Retry with exponential backoff (max 10 minutes)
        const delaySeconds = Math.min(10 * 2 ** message.attempts, 600);
        message.retry({ delaySeconds });
      } else {
        // Permanent failure: ack the message so it does NOT retry,
        // then manually enqueue to DLQ with failure metadata
        await env.DLQ_QUEUE.send({
          originalMessage: message.body,
          failureReason: result.error,
          attempts: message.attempts,
          failedAt: new Date().toISOString(),
        });
        message.ack(); // prevent auto-DLQ double-routing
      }
    }
  },
};
```

`message.attempts` is the 1-based delivery count. If you rely on the native `dead_letter_queue` config, do NOT also manually enqueue to the DLQ — you will get duplicates. Choose one pattern:
- **Native DLQ config** (simpler): call `message.retry()` on retryable failures and let `max_retries` trigger automatic DLQ routing.
- **Manual DLQ routing** (more control): always `ack()` every message and route to DLQ explicitly. Set `max_retries = 0` to disable native retries.

## Poison-Message Detection

A poison message is one that always causes the consumer to crash (uncaught exception) before it can ack or retry. Cloudflare re-queues the entire batch if the consumer throws. If one bad message is always in the batch, it blocks all subsequent messages.

Detection and isolation strategy:

```typescript
export default {
  async queue(batch: MessageBatch<JobMessage>, env: Env): Promise<void> {
    // Process each message individually with a try/catch
    // so one bad message does not poison the entire batch
    for (const message of batch.messages) {
      try {
        const result = await processJob(message.body, env);
        if (result.success) {
          message.ack();
        } else {
          message.retry();
        }
      } catch (err) {
        // Uncaught processing error
        const isPoisoned = message.attempts >= 2; // seen more than once
        if (isPoisoned) {
          // Move to DLQ immediately rather than keep retrying
          await env.DLQ_QUEUE.send({
            originalMessage: message.body,
            failureReason: String(err),
            attempts: message.attempts,
          });
          message.ack(); // remove from primary queue
        } else {
          message.retry({ delaySeconds: 30 });
        }
      }
    }
  },
};
```

Batch-level poison isolation: if messages share a batch and one crashes the Worker before the loop completes, all unacked messages replay. Set `max_batch_size = 1` for critical jobs where isolation is paramount (at the cost of throughput).

## Mobile-Triggered Queue Reliability

Mobile clients (iOS/Android example project app) trigger transcode jobs over unreliable connections. Common issues:

| Problem | Symptom | Fix |
|---|---|---|
| Duplicate enqueues | Same job processed twice | Idempotency key in message body |
| Retry storm | Network timeout causes client to retry POST, Workers API re-enqueues | Idempotency check in Workers API route before `queue.send()` |
| Partial uploads | Audio file not yet in R2 when job dequeues | Enqueue after R2 PUT completes, not before |
| Background app kill | Client thinks job was enqueued but request never reached Workers | Confirm via job status polling endpoint |

Idempotency key pattern — Workers API route:

```typescript
app.post("/api/transcode", async (c) => {
  const { fileKey, idempotencyKey } = await c.req.json();

  // Check if this idempotencyKey was already enqueued
  const existing = await c.env.DB.prepare(
    "SELECT id, status FROM jobs WHERE idempotency_key = ? LIMIT 1"
  ).bind(idempotencyKey).first<{ id: string; status: string }>();

  if (existing) {
    return c.json({ jobId: existing.id, status: existing.status, duplicate: true });
  }

  const jobId = crypto.randomUUID();
  await c.env.DB.prepare(
    "INSERT INTO jobs (id, idempotency_key, file_key, status, created_at) VALUES (?, ?, ?, 'queued', datetime('now'))"
  ).bind(jobId, idempotencyKey, fileKey).run();

  await c.env.JOBS_QUEUE.send({ jobId, fileKey });

  return c.json({ jobId, status: "queued" });
});
```

Mobile client generates `idempotencyKey = SHA-256(userId + fileKey + sessionId)` and includes it in every transcode request, including retries.

## DLQ Consumer Worker

```typescript
// workers/dlq-consumer.ts
interface DLQMessage {
  originalMessage: unknown;
  failureReason: string;
  attempts: number;
  failedAt: string;
}

export default {
  async queue(batch: MessageBatch<DLQMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const { originalMessage, failureReason, attempts, failedAt } = message.body;

      // Persist to D1 for audit
      await env.DB.prepare(
        `INSERT INTO dlq_events (id, original_payload, failure_reason, attempts, failed_at)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(
        crypto.randomUUID(),
        JSON.stringify(originalMessage),
        failureReason,
        attempts,
        failedAt
      ).run();

      // Alert via Analytics Engine
      env.AE.writeDataPoint({
        blobs: ["dlq", failureReason.slice(0, 200)],
        doubles: [attempts, 1],
      });

      message.ack();
    }
  },
};
```

Wire the DLQ consumer in `wrangler.toml`:

```toml
[[queues.consumers]]
queue = "example project-dlq-queue"
max_batch_size = 50
max_batch_timeout = 30
max_retries = 0   # DLQ messages should not re-DLQ
```

## Anti-patterns

- Setting `max_retries` very high (e.g. 20) for all messages — permanent failures waste resources for hours before landing in DLQ.
- Not catching errors per-message in the consumer loop — one bad message can block the entire batch indefinitely.
- Enqueuing jobs before the prerequisite resource (R2 file) exists — consumer fails every attempt because the file is missing.
- Using the same queue for both high-priority (mobile interactive) and low-priority (batch processing) jobs — a burst of low-priority jobs delays mobile-triggered ones; use separate queues with separate consumers.
- Manually routing to DLQ AND having `dead_letter_queue` set in config — produces duplicate DLQ entries.

## Gotchas

- **`message.retry()` vs throwing**: calling `message.retry()` delays the specific message; throwing an unhandled exception re-queues the ENTIRE UNACKED BATCH immediately. Always catch errors per-message.
- **Visibility timeout is ~30 seconds**: if `processJob` takes > 30s, the message is re-queued before the consumer acks. For long jobs, enqueue a job-start marker in D1 immediately and do the heavy work in a separate Durable Object or via `waitUntil`.
- **`max_batch_timeout` is capped at 30s**: you cannot configure a longer wait for batch accumulation.
- **DLQ is a regular queue**: it has its own `max_retries`. Set it to 0 or 1 to avoid DLQ messages bouncing in a DLQ loop.
- **Queue consumers are billed as Worker invocations**: very small `max_batch_size` on a high-throughput queue increases invocation cost significantly.
- **`send()` is not transactional with D1**: if the `DB.prepare().run()` for idempotency key insertion succeeds but `queue.send()` fails, you have a phantom job record. Wrap in a try/catch and delete the D1 row on send failure, or mark it `status = 'send_failed'`.

## Verification

```bash
# List queues
wrangler queues list

# Check DLQ depth (messages waiting)
wrangler queues consumer list example project-dlq-queue

# Manually send a test message to trigger the consumer
wrangler queues send example project-jobs-queue '{"jobId":"test-001","fileKey":"test/audio.mp3"}'

# Check DLQ events in D1
wrangler d1 execute example project-d1-prod --remote --json \
  --command "SELECT failure_reason, COUNT(*) as n FROM dlq_events GROUP BY failure_reason ORDER BY n DESC LIMIT 10"
```

## Related

- `queues-dlq-patterns.md` — earlier DLQ pattern reference
- `queues-batch-processing.md` — batch consumer configuration
- `queues-mobile-background-job-fanout.md` — mobile job fan-out patterns
- `d1-job-queue-pattern.md` — D1-backed job state tracking
- `workers-analytics-engine.md` — AE for DLQ alerting

## Sources

- Cloudflare Queues consumer docs: https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- Queues retry and DLQ: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Message ack/retry API: https://developers.cloudflare.com/queues/runtime-apis/message/
