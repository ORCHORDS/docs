# Cloudflare Queues Delayed Delivery and Message Scheduling

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to schedule work to run at a future time — send a reminder email 24h after sign-up, retry a webhook delivery 15 minutes after a failure, or publish a blog post at a specific timestamp — without running a cron job on a traditional server. Cloudflare Queues **delayed delivery** lets you enqueue a message now with a `delaySeconds` parameter so the consumer Worker does not receive it until the specified offset has elapsed.

---

## Context

Queues delayed delivery was introduced in 2024. Key properties:

| Property | Value |
|----------|-------|
| Minimum delay | 0 seconds (immediate) |
| Maximum delay | 43,200 seconds (12 hours) |
| Delay granularity | Seconds |
| Delay scope | Per-message; can be set at send time or in the consumer's `ack/retry` response |
| Retry delay | A consumer can re-delay a message on `retry()` to implement exponential backoff |

Queues still guarantee **at-least-once** delivery. A delayed message may be delivered slightly after the requested delay (never before) due to batch processing windows. Combine with an idempotency key in D1 or KV to handle duplicate deliveries safely.

Delayed delivery is not the same as a cron trigger: it is message-scoped, not time-scoped. You enqueue the message immediately and the platform holds it. This means the delay clock starts from the time of enqueue, not from a wall-clock schedule.

---

## Wrangler Configuration

```toml
# wrangler.toml
name = "scheduler-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[queues.producers]]
binding = "TASK_QUEUE"
queue = "scheduled-tasks"

[[queues.consumers]]
queue = "scheduled-tasks"
max_batch_size = 10
max_batch_timeout = 30
max_retries = 3
dead_letter_queue = "scheduled-tasks-dlq"
```

---

## Enqueuing a Delayed Message

```typescript
// src/index.ts
interface Env {
  TASK_QUEUE: Queue<ScheduledTask>;
}

interface ScheduledTask {
  taskId: string;
  type: "send_email" | "publish_post" | "webhook_retry" | "reminder";
  payload: Record<string, unknown>;
  scheduledAt: string; // ISO timestamp for audit
  idempotencyKey: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.json<{
      type: ScheduledTask["type"];
      payload: Record<string, unknown>;
      delaySeconds: number;
    }>();

    const taskId = crypto.randomUUID();
    const idempotencyKey = `${body.type}:${JSON.stringify(body.payload)}`;

    await env.TASK_QUEUE.send(
      {
        taskId,
        type: body.type,
        payload: body.payload,
        scheduledAt: new Date().toISOString(),
        idempotencyKey,
      },
      {
        delaySeconds: Math.min(body.delaySeconds, 43_200), // clamp to 12h max
        contentType: "json",
      }
    );

    return Response.json({
      ok: true,
      taskId,
      deliveryAfter: new Date(Date.now() + body.delaySeconds * 1000).toISOString(),
    });
  },
};
```

---

## Common Scheduling Patterns

### 24-Hour Post-Signup Reminder

```typescript
// Enqueue at signup time; delay 24 hours
async function scheduleWelcomeEmail(
  userId: string,
  email: string,
  queue: Queue<ScheduledTask>
): Promise<void> {
  await queue.send(
    {
      taskId: crypto.randomUUID(),
      type: "send_email",
      payload: { userId, email, template: "welcome_day1" },
      scheduledAt: new Date().toISOString(),
      idempotencyKey: `welcome_day1:${userId}`,
    },
    { delaySeconds: 86_400 } // 24 hours — exceeds 12h max, see Gotchas
  );
}
```

> **Note**: 24 hours exceeds the 12-hour maximum. See [Chain-Scheduling Beyond 12 Hours] below.

---

### Exponential Backoff Retry in the Consumer

```typescript
export default {
  async queue(batch: MessageBatch<ScheduledTask>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const task = msg.body;

      try {
        await processTask(task, env);
        msg.ack();
      } catch (err) {
        const attempt = (task.payload["_attempt"] as number | undefined) ?? 0;

        if (attempt >= 4) {
          // Max retries exceeded — let it go to the DLQ
          msg.ack(); // ack so it doesn't auto-retry; DLQ receives a copy
          await sendToDeadLetter(task, err as Error, env);
          return;
        }

        // Exponential backoff: 1m, 2m, 4m, 8m
        const backoffSeconds = Math.pow(2, attempt) * 60;

        msg.retry({
          delaySeconds: backoffSeconds,
        });

        console.log(
          `Task ${task.taskId} retry ${attempt + 1} in ${backoffSeconds}s`
        );
      }
    }
  },
};
```

---

### Chain-Scheduling Beyond 12 Hours

Since the max delay is 12 hours (43,200 seconds), chain messages to reach longer delays.

```typescript
interface ChainTask extends ScheduledTask {
  remainingDelaySeconds: number;
  hops: number;
}

async function scheduleWithLongDelay(
  task: ScheduledTask,
  totalDelaySeconds: number,
  queue: Queue<ChainTask>
): Promise<void> {
  const MAX_HOP = 43_200;
  const firstHop = Math.min(totalDelaySeconds, MAX_HOP);

  await queue.send(
    {
      ...task,
      remainingDelaySeconds: totalDelaySeconds - firstHop,
      hops: 0,
    },
    { delaySeconds: firstHop }
  );
}

// Consumer side: re-enqueue if remaining delay > 0
export default {
  async queue(batch: MessageBatch<ChainTask>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const task = msg.body;

      if (task.remainingDelaySeconds > 0) {
        const nextHop = Math.min(task.remainingDelaySeconds, 43_200);
        await env.TASK_QUEUE.send(
          { ...task, remainingDelaySeconds: task.remainingDelaySeconds - nextHop, hops: task.hops + 1 },
          { delaySeconds: nextHop }
        );
        msg.ack();
        continue;
      }

      // Actually process the task
      try {
        await processTask(task, env);
        msg.ack();
      } catch {
        msg.retry({ delaySeconds: 60 });
      }
    }
  },
};
```

---

## Idempotent Consumers with D1

At-least-once delivery means the consumer may receive the same message twice. Use D1 to track processed task IDs.

```typescript
interface Env {
  TASK_QUEUE: Queue<ScheduledTask>;
  DB: D1Database;
}

async function ensureProcessedOnce(
  db: D1Database,
  idempotencyKey: string
): Promise<boolean> {
  const result = await db
    .prepare(
      `INSERT OR IGNORE INTO processed_tasks (idempotency_key, processed_at)
       VALUES (?, ?)`
    )
    .bind(idempotencyKey, new Date().toISOString())
    .run();

  // changes = 0 means the key already existed (duplicate)
  return (result.meta.changes ?? 0) > 0;
}

export default {
  async queue(batch: MessageBatch<ScheduledTask>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const task = msg.body;

      const isNew = await ensureProcessedOnce(env.DB, task.idempotencyKey);
      if (!isNew) {
        // Already processed — silently ack the duplicate
        msg.ack();
        continue;
      }

      try {
        await processTask(task, env);
        msg.ack();
      } catch (err) {
        msg.retry({ delaySeconds: 60 });
      }
    }
  },
};
```

---

## Anti-patterns

- **Using wall-clock timestamps inside the message payload to gate processing**: the consumer receives the message after the delay, but nothing prevents the consumer from ignoring its timestamp. The delay is enforced by the platform; don't double-gate with payload-level timestamp checks unless you need business logic precision beyond the platform's granularity.
- **Setting `delaySeconds` to a value greater than 43,200**: the API rejects values above 12 hours. Use the chain-scheduling pattern.
- **Using delayed delivery as a cron replacement for high-frequency tasks**: if you need something to run every 5 minutes, use a Cron Trigger (`[triggers] crons`), not a self-re-enqueuing delayed message. The chain approach adds queue latency jitter.
- **Not setting an idempotency key**: at-least-once delivery guarantees the consumer will process each message *at least* once. Without idempotency protection, a duplicate delivery causes duplicate side effects (double emails, double charges).
- **Forgetting `dead_letter_queue` in wrangler.toml**: without a DLQ, permanently-failing messages are silently dropped after `max_retries`. Always configure a DLQ and alert on its depth.

---

## Gotchas

- The delay clock starts from the time the producer calls `queue.send()`, not from when the batch is submitted or when the consumer processes earlier messages in a batch.
- `msg.retry({ delaySeconds })` is available in the consumer at the individual message level. If you call `batch.retryAll()` without a per-message delay, all messages retry with the queue's default retry delay (usually 0).
- Messages delayed more than 1 hour may be stored in a different storage tier internally. Cloudflare does not guarantee sub-second delivery precision for long delays — expect ±30 seconds variance on 12-hour delays.
- The `contentType: "json"` option in `queue.send()` is required for the consumer to receive the message as a typed object. Without it, `msg.body` is a raw string.
- Cloudflare Queues charges for both message sends and consumer reads. A chain-scheduling pattern that makes N hops for a long delay charges N sends and N consumer invocations. Factor this into cost estimates for high-volume scheduling.

---

## Verification

```bash
# Send a test delayed message (30-second delay)
curl -X POST https://scheduler.example.com/schedule \
  -H "Content-Type: application/json" \
  -d '{"type": "send_email", "payload": {"to": "test@example.com"}, "delaySeconds": 30}'

# Monitor queue depth in the Cloudflare dashboard
# Queues → scheduled-tasks → Messages in flight

# Check DLQ for failed messages
wrangler queues consumer list scheduled-tasks-dlq

# Verify idempotency table in D1
wrangler d1 execute <DB_NAME> --command "SELECT * FROM processed_tasks ORDER BY processed_at DESC LIMIT 10"

# Test exponential backoff by triggering a consumer error
# Check Queues metrics → Retry count by message
```

---

## Related

- `cloudflare-queues-dead-letter-dlq.md`
- `queues-batch-processing.md`
- `queues-dlq-patterns.md`
- `workers-cron-triggers.md`
- `d1-best-practices.md`

---

## Sources

- https://developers.cloudflare.com/queues/configuration/delay-messages/
- https://developers.cloudflare.com/queues/reference/javascript-apis/#message
- https://developers.cloudflare.com/queues/get-started/
- https://developers.cloudflare.com/queues/reference/how-queues-works/
