# Workers Queues Max Retries Exceeded Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

Notification emails and webhook deliveries stopped being sent for roughly 90 minutes.
The Cloudflare dashboard showed the queue's `messages_failed` metric climbing steadily while
`messages_delivered_success` dropped to zero. The dead-letter queue (DLQ) accumulated ~14 000
messages, none of which was automatically reprocessed. Customer support received escalations
about missed order confirmation emails within 20 minutes of the incident start.

## Context

The team used a Workers Queue (`notifications-queue`) with `max_retries = 3` and a consumer
Worker that called an internal email service. A deploy shipped a misconfigured SMTP credentials
secret (`SENDGRID_KEY` pointed at the staging namespace value in production). Every message
failed with HTTP 403 from SendGrid. After 3 retries each message landed in the DLQ. Because
the DLQ had no consumer Worker bound, messages silently accumulated with no alert, no
reprocessing path, and no runbook.

---

## Root Cause: Failing Closed Without a DLQ Consumer

```typescript
// wrangler.toml — queue binding BEFORE fix
// [[queues.consumers]]
// queue = "notifications-queue"
// max_retries = 3
// dead_letter_queue = "notifications-dlq"   ← DLQ defined but no consumer bound

// AFTER fix: add a consumer for the DLQ that emits structured alerts
// [[queues.consumers]]
// queue = "notifications-dlq"
// max_batch_size = 10
// max_batch_timeout = 5
```

```typescript
// src/consumers/dlq-consumer.ts
export default {
  async queue(batch: MessageBatch<NotificationMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      // Emit a high-severity alert — PagerDuty / Slack via Analytics Engine
      console.error('DLQ message received', {
        messageId: msg.id,
        attempts: msg.attempts,
        body: msg.body,
      });

      // Optionally: write to R2 for forensic replay
      const key = `dlq/${new Date().toISOString()}/${msg.id}.json`;
      await env.DEAD_LETTERS.put(key, JSON.stringify({ msg: msg.body, ts: Date.now() }));

      msg.ack(); // Acknowledge so DLQ does not re-enqueue
    }
  },
};
```

## Retry Budget Awareness: Log Remaining Retries

```typescript
// src/consumers/notification-consumer.ts
interface NotificationMessage {
  userId: string;
  templateId: string;
  to: string;
}

export default {
  async queue(batch: MessageBatch<NotificationMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const remainingRetries = (msg as any).attempts !== undefined
        ? (3 - Number((msg as any).attempts))
        : 'unknown';

      try {
        await sendEmail(env, msg.body);
        msg.ack();
      } catch (err) {
        console.warn('Notification delivery failed', {
          msgId: msg.id,
          remainingRetries,
          error: String(err),
        });
        // Do NOT call msg.ack() — let the queue framework retry
        msg.retry({ delaySeconds: 30 }); // explicit delay between retries
      }
    }
  },
};

async function sendEmail(env: Env, payload: NotificationMessage): Promise<void> {
  const res = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    signal: AbortSignal.timeout(10_000),
    headers: {
      Authorization: `Bearer ${env.SENDGRID_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ /* … */ }),
  });

  if (res.status === 401 || res.status === 403) {
    // Credentials failure — retrying will not help; explicitly route to DLQ.
    // Calling retry() here still counts against max_retries, but we want
    // the DLQ consumer to catch and alert rather than silently exhaust.
    throw new Error(`SendGrid auth failure: ${res.status}`);
  }

  if (!res.ok) throw new Error(`SendGrid error ${res.status}`);
}
```

## Non-Retryable Error Fast Path

```typescript
// Distinguish transient vs permanent failures to avoid burning retry budget
// on errors that will never succeed (bad credentials, invalid recipient, etc.)

const NON_RETRYABLE = new Set([400, 401, 403, 422]);

export default {
  async queue(batch: MessageBatch<NotificationMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        const statusCode = await trySendEmail(env, msg.body);
        msg.ack();
      } catch (err: any) {
        if (err.statusCode && NON_RETRYABLE.has(err.statusCode)) {
          // Immediately route to DLQ — no point retrying
          msg.ack();
          // Write to R2 for manual reprocessing after credentials are fixed
          await env.DEAD_LETTERS.put(
            `permanent-failure/${msg.id}.json`,
            JSON.stringify({ body: msg.body, statusCode: err.statusCode, ts: Date.now() }),
          );
          console.error('Permanent failure — message moved to R2', { msgId: msg.id });
        } else {
          // Transient — let the queue retry
          msg.retry({ delaySeconds: 60 });
        }
      }
    }
  },
};
```

## DLQ Replay After Credentials Fix

```typescript
// src/scripts/replay-dlq.ts  (run with `wrangler run` or as a Cron Trigger)
// After fixing SENDGRID_KEY, re-enqueue DLQ messages from R2

export async function replayDlqFromR2(env: Env): Promise<{ replayed: number }> {
  const listed = await env.DEAD_LETTERS.list({ prefix: 'permanent-failure/' });
  let replayed = 0;

  for (const obj of listed.objects) {
    const raw = await env.DEAD_LETTERS.get(obj.key);
    if (!raw) continue;

    const { body } = JSON.parse(await raw.text()) as { body: NotificationMessage };
    await env.NOTIFICATIONS_QUEUE.send(body);
    await env.DEAD_LETTERS.delete(obj.key);
    replayed++;
  }

  return { replayed };
}
```

## Alerting on Max Retries Exhaustion

```typescript
// Use Workers Analytics Engine to emit a metric when entering DLQ consumer
// so dashboards can alert before the backlog grows unbounded.

export default {
  async queue(batch: MessageBatch<NotificationMessage>, env: Env): Promise<void> {
    env.ANALYTICS.writeDataPoint({
      blobs: ['dlq', 'notifications-dlq'],
      doubles: [batch.messages.length],
      indexes: ['dlq_arrival'],
    });
    // … rest of DLQ consumer
  },
};
```

---

## Anti-Patterns

- **Defining a DLQ without a consumer Worker.** Messages accumulate silently; there is no
  alert, no visibility, and no recovery path.
- **Treating all errors as retryable.** Auth failures, invalid recipient addresses, and
  malformed payloads will never succeed on retry; burning retry budget only delays the DLQ
  arrival and masks the real error.
- **Not logging `msg.attempts` or remaining retries.** Without this, the last attempt looks
  identical to the first in logs, making RCA impossible.
- **Relying on `max_retries` as the only circuit breaker.** If every message fails, the
  queue will drain its retry budget before any alert fires.

## Gotchas

- `msg.retry({ delaySeconds })` is only available in consumers bound to a queue with
  `delivery_delay` support. Check `wrangler` version if the field is ignored.
- Messages that call neither `ack()` nor `retry()` are implicitly retried by the runtime
  when the consumer Worker throws. This is usually correct, but can cause double retries if
  your code calls `retry()` and then also throws.
- DLQ consumers have the same `max_retries` default (3). If you do not `ack()` in the DLQ
  consumer, messages re-enter the DLQ of the DLQ — which likely does not exist, causing
  silent loss.
- Queue consumer scaling is tied to the `max_concurrency` setting. Under sustained high load
  the concurrency cap itself can cause messages to exceed their `visibility_timeout` and be
  delivered twice.

## Verification

```bash
# Confirm DLQ has a consumer bound
wrangler queues consumer list notifications-dlq

# Check DLQ backlog size in the dashboard or via API
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues?name=notifications-dlq" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[0].consumers_total_count'

# Replay from R2 after credentials are corrected
wrangler run --env=production scripts/replay-dlq.ts
```

## Related

- `queues-consumer-crash-loop-dlq-overflow-postmortem.md`
- `queues-consumer-visibility-timeout-retry-storm-postmortem.md`
- `queues-consumer-scaling-backpressure-lesson.md`
- `queue-consumers-must-be-idempotent.md`
- `retry-storm-queue-poison-message.md`

## Sources

- Workers Queues dead letter queues: https://developers.cloudflare.com/queues/reference/dead-letter-queues/
- Workers Queues consumer configuration: https://developers.cloudflare.com/queues/configuration/consumer-workers/
- `msg.retry` with delay: https://developers.cloudflare.com/queues/reference/javascript-apis/#messagebatch
