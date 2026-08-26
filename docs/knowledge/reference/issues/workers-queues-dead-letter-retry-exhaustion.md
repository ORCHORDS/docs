# Workers Queues Dead-Letter Queue and Retry Exhaustion Debugging

2026-08-24 / example.com / production

---

## Symptom / Use-case

Messages sent to a Cloudflare Workers Queue are being consumed by the queue consumer Worker but not successfully processed. After several automatic retries the messages disappear from the queue without any record of what happened to them, or conversely they loop indefinitely, exhausting retries and causing the queue consumer to be rate-throttled.

Specific patterns reported:
- A queue consumer Worker throws an unhandled exception; the message is retried up to 3 times (default) then silently dropped
- Messages that fail schema validation are retried identically each time, wasting all retry attempts before landing in the dead-letter queue (DLQ)
- The DLQ itself fills up but no alerting fires; stale failed messages accumulate
- A consumer that calls an external API gets a transient 503; the retry delay is too short and all retries hit the same outage window, exhausting the budget

---

## Context

Cloudflare Queues delivers messages to a consumer Worker via the `queue` handler. Key properties of the retry and DLQ system:

- **Default max retries**: 3 attempts per message (configurable up to the platform maximum)
- **Default retry delay**: exponential backoff starting at ~10 s; total window depends on configuration
- **Dead-letter queue**: an optional secondary queue where permanently failed messages are sent after exhausting retries. You must create the DLQ queue and configure `dead_letter_queue` in `wrangler.toml`
- **`message.retry()`**: explicitly re-enqueues the current message (resets its delivery count); use sparingly — this creates a new message with a fresh retry counter
- **`message.ack()`**: marks the message as successfully processed; removes it from the queue permanently
- **Batch semantics**: the `queue` handler receives a `MessageBatch`. If the handler throws, **all messages in the batch** are retried. If you call `batch.ackAll()` before throwing, none are retried

Understanding whether a failure is transient (retry worthwhile) vs. permanent (retry wasteful) is the core design decision.

---

## Diagnosing Retry Exhaustion and DLQ Issues

### Step 1 — Make retry decisions explicit per message

```typescript
// src/queue-consumer.ts
export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processMessage(message.body, env);
        message.ack();
      } catch (err) {
        const isTransient = isTransientError(err);

        if (isTransient && message.attempts < 3) {
          // Explicitly retry with a delay
          message.retry({ delaySeconds: Math.pow(2, message.attempts) * 10 });
          console.warn(JSON.stringify({
            event: 'message.retry',
            id: message.id,
            attempt: message.attempts,
            delay_s: Math.pow(2, message.attempts) * 10,
            error: String(err),
          }));
        } else {
          // Permanent failure or retry budget exhausted — ack to prevent infinite loop
          // The message will land in the DLQ if configured
          message.ack();
          console.error(JSON.stringify({
            event: 'message.permanent_failure',
            id: message.id,
            attempt: message.attempts,
            body: JSON.stringify(message.body),
            error: String(err),
          }));
          // Emit to Analytics Engine for alerting
          env.ANALYTICS.writeDataPoint({
            blobs: [message.id, String(err)],
            doubles: [message.attempts],
            indexes: ['queue-dlq-event'],
          });
        }
      }
    }
  },
};

function isTransientError(err: unknown): boolean {
  if (err instanceof Response) return err.status >= 500 && err.status !== 501;
  if (err instanceof TypeError && String(err).includes('fetch failed')) return true;
  return false;
}
```

### Step 2 — Validate message schema before any processing

```typescript
// src/queue-consumer.ts (schema validation guard)
import { z } from 'zod';

const OrderMessageSchema = z.object({
  orderId: z.string().uuid(),
  sku: z.string().min(1),
  qty: z.number().int().positive(),
});

type OrderMessage = z.infer<typeof OrderMessageSchema>;

async function processMessage(body: unknown, env: Env): Promise<void> {
  const parsed = OrderMessageSchema.safeParse(body);
  if (!parsed.success) {
    // Schema failure is permanent — do not retry; log and move on
    throw Object.assign(
      new Error('schema_validation_failure'),
      { permanent: true, detail: parsed.error.format() }
    );
  }
  await fulfillOrder(parsed.data, env);
}
```

### Step 3 — Configure DLQ in wrangler.toml

```toml
# wrangler.toml
[[queues.consumers]]
queue = "order-processing"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "order-processing-dlq"
retry_delay = "10s"
```

### Step 4 — Consume and inspect the DLQ

```typescript
// src/dlq-consumer.ts
// A separate Worker that consumes the dead-letter queue for analysis and alerting
export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      // Store failed messages for human review
      const key = `dlq/${new Date().toISOString().slice(0, 10)}/${message.id}`;
      await env.FAILED_MESSAGES_KV.put(
        key,
        JSON.stringify({
          id: message.id,
          body: message.body,
          attempts: message.attempts,
          timestamp: new Date().toISOString(),
        }),
        { expirationTtl: 60 * 60 * 24 * 30 } // keep for 30 days
      );

      // Alert via a webhook (e.g., Slack, PagerDuty)
      await notifyDlqEvent(message, env);
      message.ack();
    }
  },
};

async function notifyDlqEvent(message: Message<unknown>, env: Env): Promise<void> {
  const payload = {
    text: `Queue DLQ event: message ${message.id} failed after ${message.attempts} attempts`,
    body_preview: JSON.stringify(message.body).slice(0, 200),
  };
  await fetch(env.ALERT_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(5_000),
  });
}
```

### Step 5 — Replay DLQ messages after fixing the root cause

```typescript
// src/dlq-replay.ts
// Called manually or via a scheduled Worker after the underlying bug is fixed
export async function replayDlqMessages(
  env: Env,
  limit = 100
): Promise<{ replayed: number; errors: number }> {
  const keys = await env.FAILED_MESSAGES_KV.list({ prefix: 'dlq/', limit });
  let replayed = 0;
  let errors = 0;

  for (const key of keys.keys) {
    const raw = await env.FAILED_MESSAGES_KV.get(key.name, { type: 'json' });
    if (!raw) continue;

    try {
      await env.ORDER_QUEUE.send((raw as { body: unknown }).body);
      await env.FAILED_MESSAGES_KV.delete(key.name);
      replayed++;
    } catch (err) {
      console.error(`replay failed for ${key.name}:`, err);
      errors++;
    }
  }

  console.log(`DLQ replay complete: ${replayed} replayed, ${errors} errors`);
  return { replayed, errors };
}
```

### Step 6 — Track retry exhaustion rate with Analytics Engine

```typescript
// src/queue-metrics.ts
export function emitQueueMetric(
  ae: AnalyticsEngineDataset,
  event: 'ack' | 'retry' | 'dlq',
  messageId: string,
  attempts: number
): void {
  ae.writeDataPoint({
    blobs: [event, messageId],
    doubles: [attempts],
    indexes: [`queue-${event}`],
  });
}
```

Query in Analytics Engine GraphQL to alert when DLQ rate spikes:

```sql
SELECT
  SUM(_sample_interval) AS dlq_count,
  toStartOfFiveMinutes(timestamp) AS bucket
FROM queue_dlq_event
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY bucket
ORDER BY bucket DESC
```

---

## Anti-patterns

- **Letting the consumer handler throw without per-message handling** — an unhandled throw retries the entire batch; one bad message in a batch of 10 blocks all 10 messages' delivery.
- **Calling `message.retry()` unconditionally** — `retry()` re-enqueues with a fresh counter; looping on retry() for a permanently broken message creates an infinite loop that wastes queue throughput.
- **Not configuring a DLQ** — without a DLQ, messages that exhaust retries are **silently dropped** with no audit trail.
- **Using the same retry delay for all error types** — a 503 from an overloaded API benefits from exponential backoff; a schema validation error benefits from immediate ack-to-DLQ. Treat error types differently.
- **Retrying inside the handler with `await processMessage()` in a loop** — this holds the queue consumer open longer, consuming CPU time and potentially triggering the Worker CPU limit; delegate retry logic to the queue's built-in retry mechanism instead.

---

## Gotchas

- `message.attempts` starts at **1** on the first delivery, not 0. A `max_retries = 3` configuration allows deliveries at attempts 1, 2, 3, and 4 (total 4 attempts) in some platform versions; verify your platform's counting convention in the Cloudflare dashboard.
- The `dead_letter_queue` must be a **separately created queue** — specifying a queue name that does not exist silently disables DLQ routing; messages are dropped after retry exhaustion with no error.
- `batch.retryAll()` and `batch.ackAll()` affect **all messages in the current batch** — use per-message `message.ack()` and `message.retry()` when messages have independent failure domains.
- Queue consumers are subject to the Workers **CPU time limit**. A consumer that processes a batch of 100 messages with complex per-message logic can exceed CPU limits; lower `max_batch_size` or move heavy processing to a chained Worker.
- `retry_delay` in `wrangler.toml` sets the **minimum** delay before re-delivery. The platform may add additional jitter; do not design systems that require precise retry timing.
- Messages sent to the DLQ are **new messages** with a fresh body; the original `message.id` is preserved in the body only if you explicitly include it when the producer sends.

---

## Verification

1. Send 5 intentionally malformed messages to the queue. Confirm they exhaust retries (check attempt count in logs from Step 1) and land in the DLQ consumer (Step 4).
2. Verify DLQ storage entries appear in KV under the `dlq/` prefix.
3. Fix the processing logic and run the replay script (Step 5). Confirm the replayed messages succeed and KV entries are cleaned up.
4. Query Analytics Engine (Step 6) and verify `dlq` events appear only for the broken messages, and `ack` events appear for successful processing.
5. Simulate a transient error (e.g., mock upstream returning 503) and confirm exponential backoff delays are applied before final DLQ routing.

---

## Related

- `worker-cpu-limit-exceeded.md`
- `worker-subrequest-limit.md`
- `workers-kv-cold-read-performance.md`
- `platform-health-score-dashboard-analytics-engine.md`

---

## Sources

- Cloudflare Queues — Consumer Workers: https://developers.cloudflare.com/queues/reference/how-queues-works/#consumers
- Cloudflare Queues — Batching and Retries: https://developers.cloudflare.com/queues/configuration/batching-retries/
- Cloudflare Queues — Dead-Letter Queues: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
