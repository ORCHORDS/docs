# Queues Consumer Visibility Timeout Retry Storm Postmortem

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

A Cloudflare Queue was used to fan-out order-processing jobs to a consumer Worker. During a dependency outage (a downstream payment processor returning 503s), the consumer Worker correctly caught exceptions and did not call `message.ack()`. The expectation was that the Queue would redeliver messages after the visibility timeout, with the consumer retry logic providing a natural backoff. Instead, the Queue entered a retry storm: every previously invisible message became visible simultaneously at the end of each visibility timeout window, overwhelming both the consumer Worker and the payment processor with a burst of thousands of concurrent retries. The consumer Worker hit the Workers CPU burst limit, and the payment processor rate-limited the entire account. The storm repeated every `visibilityTimeoutSecs` seconds for 38 minutes until an engineer manually purged the queue.

## Context

Cloudflare Queues uses a pull-based model internally but exposes a push-based consumer interface to Workers. When a consumer Worker does not acknowledge a message (either by calling `message.ack()` or letting the handler return without calling `message.retry()`), the Queue makes the message visible again after the `visibilityTimeoutSecs` setting. If many messages were enqueued roughly simultaneously (e.g., a batch from a webhook fan-out), they all become visible at the same time at the end of every visibility window. This "thundering herd" on the consumer is a well-known distributed systems problem; Cloudflare Queues does not currently implement jittered or exponential redelivery by default. Operators must implement retry jitter themselves.

---

## 1. The Retry Storm Mechanism

```
T=0:      1,000 messages enqueued (batch from order webhook)
T=30s:    Consumer invocations fail — messages return to invisible
T=60s:    visibilityTimeoutSecs=30 → all 1,000 messages visible again
T=60s:    Consumer spawns 1,000 concurrent invocations — storm #1
T=90s:    All fail again — messages invisible
T=120s:   All visible again — storm #2
... repeats every 30 s until messages exhaust maxRetries or queue is purged
```

A `maxRetries` of 3 (the default) means 3 × storm_size total invocations above baseline throughput — in this case 3,000 — in addition to the normal queue drain load.

---

## 2. Implementing Per-Message Retry Jitter

Since Cloudflare Queues does not natively support jittered redelivery, implement it at the consumer layer by writing a "retry metadata" record to KV or D1 and calling `message.ack()` (removing from queue) after scheduling a re-enqueue with a random delay.

```typescript
// consumer-worker/src/index.ts
interface OrderMessage {
  orderId: string;
  attempt: number; // tracked in the message body
  enqueuedAt: number;
}

const MAX_ATTEMPTS = 5;
const BASE_DELAY_MS = 2_000;
const MAX_DELAY_MS = 120_000;

function jitteredDelay(attempt: number): number {
  // Exponential backoff with full jitter
  const exp = Math.min(BASE_DELAY_MS * Math.pow(2, attempt), MAX_DELAY_MS);
  return Math.floor(Math.random() * exp);
}

export default {
  async queue(batch: MessageBatch<OrderMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const body = message.body;

      if (body.attempt >= MAX_ATTEMPTS) {
        console.error(`Order ${body.orderId} exhausted retries — sending to DLQ`);
        // Write to a dead-letter KV namespace or D1 table for human review
        await env.DLQ_KV.put(
          `failed:${body.orderId}`,
          JSON.stringify({ ...body, failedAt: Date.now() }),
          { expirationTtl: 60 * 60 * 24 * 7 } // keep for 7 days
        );
        message.ack(); // remove from queue permanently
        continue;
      }

      try {
        await processOrder(body.orderId, env);
        message.ack();
      } catch (e) {
        console.warn(`Order ${body.orderId} attempt ${body.attempt} failed:`, e);

        // Ack the message NOW (remove it from queue) and re-enqueue with jitter
        message.ack();

        const delayMs = jitteredDelay(body.attempt);
        // Cloudflare Queues does not natively support delayed sends, so we use
        // a Durable Object alarm or a scheduled Worker to re-enqueue after the delay.
        // Here we write to a "retry inbox" KV key that a Cron Worker picks up.
        await env.RETRY_KV.put(
          `retry:${Date.now() + delayMs}:${body.orderId}`,
          JSON.stringify({ ...body, attempt: body.attempt + 1 }),
          { expirationTtl: 3600 }
        );
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 3. Retry Scheduler Worker (Cron-Based Re-Enqueue)

```typescript
// retry-scheduler/src/index.ts
// Runs every minute via cron trigger: "* * * * *"

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const now = Date.now();
    // List retry keys whose scheduled-at timestamp has passed
    const listed = await env.RETRY_KV.list({ prefix: "retry:" });

    for (const key of listed.keys) {
      const parts = key.name.split(":");
      const scheduledAt = parseInt(parts[1], 10);

      if (scheduledAt <= now) {
        const raw = await env.RETRY_KV.get(key.name);
        if (!raw) continue;

        const message = JSON.parse(raw) as { orderId: string; attempt: number };
        // Re-enqueue into the main queue
        await env.ORDER_QUEUE.send(message);
        await env.RETRY_KV.delete(key.name);
        console.log(`Re-enqueued order ${message.orderId} (attempt ${message.attempt})`);
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 4. Durable Object Alarm Alternative (Lower Latency)

For sub-minute delay precision, use a Durable Object alarm instead of a Cron Worker.

```typescript
// retry-do/src/index.ts
export class RetryScheduler {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async scheduleRetry(body: { orderId: string; attempt: number }, delayMs: number): Promise<void> {
    const fireAt = Date.now() + delayMs;
    await this.state.storage.put(`retry:${body.orderId}`, body);
    // Set alarm to the nearest upcoming retry time
    const existing = await this.state.storage.getAlarm();
    if (!existing || existing > fireAt) {
      await this.state.storage.setAlarm(fireAt);
    }
  }

  async alarm(): Promise<void> {
    const now = Date.now();
    const allPending = await this.state.storage.list<{ orderId: string; attempt: number }>({
      prefix: "retry:",
    });

    for (const [key, body] of allPending) {
      await this.env.ORDER_QUEUE.send(body);
      await this.state.storage.delete(key);
    }

    // Schedule next alarm if more retries were added during processing
    const remaining = await this.state.storage.list({ prefix: "retry:" });
    if (remaining.size > 0) {
      await this.state.storage.setAlarm(now + 5_000); // re-check in 5 s
    }
  }
}
```

---

## 5. Monitoring the Queue Depth During an Incident

Cloudflare Queues exposes queue depth via the Analytics Engine binding (when enabled) and Logpush. Use the REST API for operational checks.

```typescript
// scripts/queue-depth-check.ts
async function getQueueDepth(accountId: string, queueId: string, apiToken: string) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/queues/${queueId}`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const data = (await res.json()) as {
    result: { consumers_total_count: number; messages_total_count: number };
  };
  console.log("Queue depth:", data.result.messages_total_count);
  console.log("Active consumers:", data.result.consumers_total_count);
}
```

---

## Anti-patterns

- Relying on Cloudflare Queues' built-in `visibilityTimeoutSecs` as a retry backoff mechanism — it provides uniform redelivery timing, which produces thundering-herd storms when many messages fail simultaneously.
- Setting `maxRetries` to a high value (e.g., 10) without jitter — each retry wave is as large as the original failure burst, and the waves compound for 10 cycles.
- Using the DLQ binding as the primary failure signal and ignoring queue depth growth — by the time messages reach the DLQ, the retry storm has already run its course.
- Calling `message.retry()` explicitly without delay inside the consumer — this immediately returns the message to the queue, removing even the natural visibility timeout buffer.
- Purging the queue as the first response to a retry storm without understanding root cause — purging removes all messages including ones that have not yet been attempted.

## Gotchas

- Cloudflare Queues does not support native delayed sends (scheduled delivery at a future timestamp) as of 2026. Delay must be implemented at the application layer via KV, D1, or Durable Object alarms.
- The `batch.messages` array in a consumer invocation can contain messages from different original enqueue times. A uniform failure of all messages in a batch causes all of them to share the same redelivery window.
- `message.ack()` within a batch handler is idempotent — calling it more than once on the same message is safe. `message.retry()` re-queues immediately regardless of visibility timeout.
- The Queue consumer's `maxConcurrency` setting limits parallel Worker invocations but does not spread out redelivery timing; all concurrent invocations still receive the same visibility-window message cohort.
- Worker CPU time limits apply per-invocation; a burst of 1,000 simultaneous consumer invocations each near the CPU time limit can trigger the account-level Workers CPU burst limit, causing additional 429 errors on top of the downstream failures.

## Verification

```bash
# Check queue message count via Wrangler
wrangler queues list

# Check consumer configuration (visibilityTimeoutSecs, maxRetries)
wrangler queues consumer get <queue-name>

# During an incident: purge only after confirming root cause is resolved
wrangler queues purge <queue-name>  # destructive — use with caution

# Confirm retry KV keys are accumulating as expected (not storm-reattempting)
wrangler kv key list --namespace-id $RETRY_KV_NAMESPACE_ID --prefix "retry:" | head -20
```

## Related

- `cloudflare-queues-duplicate-delivery-incident.md`
- `queues-consumer-scaling-backpressure-lesson.md`
- `retry-storm-queue-poison-message.md`
- `queue-consumers-must-be-idempotent.md`
- `queue-backlog-death-spirals.md`
- `durable-object-alarm-silent-failure-payment-reminders.md`

## Sources

- Cloudflare Queues consumer configuration: https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- Cloudflare Queues message retries: https://developers.cloudflare.com/queues/reference/message-retries/
- AWS SQS jitter pattern (reference): https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Durable Object alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
