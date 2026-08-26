# workers-queues-patterns

**Issue:** Use CF Queues for async work, retries, dead-letter
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need to send an email after a user signs up. The email
API is slow (1s). The user waits 1s for the response. You
move the email to a cron. The cron runs every 5 min; some
emails are sent 5 min late.

## Root cause
**Synchronous work blocks the response.** Async work (via
queue) doesn't.

**Source:** CF Queues:
https://developers.cloudflare.com/queues/

> "Cloudflare Queues allow you to decouple your
> application into separate Workers that produce and
> consume messages."

## The "produce" pattern

```ts
// In a Worker
async function enqueueEmail(to: string, subject: string, body: string, env: Env): Promise<void> {
  await env.EMAIL_QUEUE.send({
    to,
    subject,
    body,
    enqueuedAt: new Date().toISOString(),
  });
}
```

The message is added to the queue. The Worker returns
immediately.

## The "consume" pattern

```ts
// In a separate Worker
export default {
  async queue(batch: MessageBatch<EmailMessage>, env: Env, ctx: ExecutionContext): Promise<void> {
    for (const message of batch.messages) {
      try {
        await sendEmail(message.body, env);
        message.ack();  // Mark as processed
      } catch (err) {
        message.retry({ delaySeconds: 60 });  // Retry in 1 min
      }
    }
  },
};
```

The queue worker processes the messages; the producer is
unblocked.

## The "retry" pattern

```ts
// Manual retry
message.retry({ delaySeconds: 60 * Math.pow(2, message.attempts) });
// 1st retry: 60s
// 2nd retry: 120s
// 3rd retry: 240s
// ...
```

The exponential backoff prevents overwhelming the
downstream.

## The "dead-letter queue" pattern

For messages that fail repeatedly, send to a DLQ:
```ts
const MAX_ATTEMPTS = 5;

if (message.attempts >= MAX_ATTEMPTS) {
  await env.DLQ.send({
    originalMessage: message.body,
    error: String((err as Error).message),
    failedAt: new Date().toISOString(),
  });
  message.ack();  // Ack to remove from the queue
} else {
  message.retry();
}
```

A DLQ captures the failures; you can inspect them later.

## The "batch" pattern

For high throughput, batch messages:
```ts
export default {
  async queue(batch: MessageBatch<EmailMessage>, env: Env): Promise<void> {
    // Group by recipient
    const grouped = new Map<string, EmailMessage[]>();
    for (const msg of batch.messages) {
      const key = msg.body.to;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(msg.body);
    }

    // Send one email with multiple subjects
    for (const [to, messages] of grouped) {
      try {
        await sendDigestEmail(to, messages, env);
        for (const msg of batch.messages.filter(m => m.body.to === to)) {
          msg.ack();
        }
      } catch (err) {
        for (const msg of batch.messages.filter(m => m.body.to === to)) {
          msg.retry();
        }
      }
    }
  },
};
```

The consumer batches multiple messages into a single
operation.

## The "queue vs cron" choice

| Use case | Use |
|---|---|
| Real-time response (e.g. email after signup) | Queue |
| Periodic work (e.g. daily digest) | Cron |
| Both (real-time + periodic) | Both |

For real-time, queue is faster (no waiting for the cron
tick).

## The "message idempotency" pattern

For at-least-once delivery (default), messages may be
processed multiple times:
```ts
const idempotencyKey = message.body.id;
const alreadyProcessed = await env.KV.get(`processed:${idempotencyKey}`);

if (alreadyProcessed) {
  message.ack();  // Skip
  return;
}

await processMessage(message.body, env);
await env.KV.put(`processed:${idempotencyKey}`, '1', { expirationTtl: 86400 });
message.ack();
```

The idempotency key prevents double-processing.

## The "queue depth monitoring" pattern

```ts
// In a Worker, periodically check queue depth
export async function handleScheduled(event: ScheduledEvent, env: Env): Promise<void> {
  // Note: CF doesn't expose queue depth directly
  // Use the dashboard or API
}
```

For alerts, use the CF dashboard or a custom metric.

## The "queue + DO" pattern

For stateful processing (e.g. rate limiting per user), use
a DO with a queue:
```ts
export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const id = env.PROCESSOR.idFromName(message.body.userId);
      const processor = env.PROCESSOR.get(id);
      await processor.fetch('https://processor/', { method: 'POST', body: JSON.stringify(message.body) });
      message.ack();
    }
  },
};
```

The DO holds the per-user state; the queue feeds it.

## The "queue binding" pattern

```toml
# wrangler.toml
[[queues.producers]]
binding = "EMAIL_QUEUE"
queue = "email-queue"

[[queues.consumers]]
queue = "email-queue"
max_batch_size = 10
max_batch_timeout = 30
max_retries = 5
dead_letter_queue = "email-dlq"
```

The producer and consumer are configured in `wrangler.toml`.

## The "queue cost" pattern

CF Queues cost:
- **Operations:** $0.40 per million
- **Storage:** Free for first 1 GB; $0.20 per GB-month after

For 1M messages/day, that's $12/month. Cheap.

## The "queue + cron" combo

For complex workflows, use both:
- **Queue:** Real-time events
- **Cron:** Periodic batch work

```ts
// Real-time: enqueue
await env.QUEUE.send({ type: 'user_signup', userId: 'u_123' });

// Periodic: cron worker that processes pending items
export async function handleScheduled(event: ScheduledEvent, env: Env): Promise<void> {
  // Process items that haven't been processed in 24h
}
```

## Verification
- **Test:** `test/queue.test.ts > message is processed within
  60s of enqueue` — passes
- **Live:** Queue depth + processing rate are monitored
- **Audit:** Monthly review of queue patterns

## Gotchas
- **The "queue is at-least-once" gotcha.** Messages may be
  processed multiple times. Use idempotency keys.
- **The "queue has a max message size" gotcha.** 128 KB per
  message. For larger payloads, store in R2 and pass the
  URL.
- **The "queue has a max batch size" gotcha.** 100 messages
  per batch. For higher throughput, the consumer must
  scale.
- **The "queue doesn't support delayed messages" gotcha.**
  (CF added this; check the current docs.) For now, use
  the `delaySeconds` option on `retry`.
- **The "DLQ messages must be inspected" gotcha.** A DLQ
  that grows forever is a bug. Add a monitoring alert.

## Related
- `cloudflare/workers-resource-limits.md`
- `saga-pattern.md`
- `idempotency-keys.md`
- `retry-with-exponential-backoff.md`
- `safe-deploy-checklist.md`
- CF Queues: https://developers.cloudflare.com/queues/
