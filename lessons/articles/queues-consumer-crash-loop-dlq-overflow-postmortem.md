# Queues Consumer Crash Loop DLQ Overflow Postmortem

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The example project notification delivery pipeline stopped delivering push notifications and email digests. The Cloudflare Queue consumer Worker responsible for processing outbound notification jobs entered a crash loop: it would dequeue a batch, throw an unhandled exception, allow the messages to be redelivered, and immediately crash again on the same messages. After the maximum retry count was exhausted, messages were routed to the Dead Letter Queue (DLQ). Within 4 hours, the DLQ was full and Cloudflare began dropping new messages entirely, silently discarding notification jobs.

## Context

example project sends push notifications, emails, and in-app badges via a Cloudflare Queue. The consumer Worker (`notification-consumer`) processes batches of `NotificationJob` messages, calling third-party APIs (Expo push, Resend email). A deploy introduced a malformed Zod schema that caused the consumer to throw a `ZodError` on every message in the batch — including retried messages. Since the exception escaped the per-message try/catch and propagated to the batch handler, all messages in the batch were marked for redelivery simultaneously.

## Timeline

- **07:15 UTC** — Engineer deploys `notification-consumer@v2.4.1` with updated Zod validation schema.
- **07:16 UTC** — Consumer begins processing first batch; `ZodError` thrown on every message.
- **07:16 UTC** — Cloudflare marks entire batch for redelivery (default retry after ~30 seconds).
- **07:17 UTC** — Alert fires: `notification_consumer_error_rate = 100%`.
- **07:19 UTC** — On-call engineer investigates; sees consistent `ZodError: invalid_type expected string, received undefined` in logs.
- **07:25 UTC** — Engineer identifies schema mismatch but cannot push a fix until CI passes (~8 minutes).
- **07:33 UTC** — Hotfix deployed (`notification-consumer@v2.4.2`) with schema corrected.
- **07:35 UTC** — Consumer processes backlog normally; DLQ accumulation stops.
- **08:10 UTC** — DLQ replay initiated; ~4,200 messages replayed successfully.
- **09:30 UTC** — DLQ empty; all backlogged notifications delivered (with 2h15m delay).
- **11:00 UTC** — Post-mortem review.

**Secondary incident (07:35 – 09:30 UTC):** During DLQ accumulation, Cloudflare's per-queue DLQ storage limit was approached. At peak, ~38,000 messages were in the DLQ. Cloudflare docs warn that DLQ overflow causes silent message drops — the platform was within ~5,000 messages of this threshold.

## Root Cause

Two compounding bugs:

**Bug 1 — Schema mismatch causing universal crash:**

```typescript
// workers/notification-consumer.ts — BUGGY VERSION

// New Zod schema introduced in v2.4.1
const NotificationJobSchema = z.object({
  userId: z.string(),
  type: z.enum(["push", "email", "badge"]),
  payload: z.object({
    title: z.string(),
    body: z.string(),
    // BUG: added required field not present in messages enqueued under v2.4.0
    templateVersion: z.string(), // ← was optional in producer, became required in consumer
  }),
  createdAt: z.number(),
});

export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      // BUG: ZodError thrown here escapes the loop and propagates to the batch handler
      const job = NotificationJobSchema.parse(message.body); // throws on every message
      await processNotification(job, env);
      message.ack();
    }
    // Never reached — entire batch is implicitly retried
  },
};
```

**Bug 2 — Missing per-message error isolation:**

The crash of one message inside the loop aborted processing of all subsequent messages in the batch. None were acked, so all were redelivered. The correct pattern is to catch per-message errors and call `message.retry()` or `message.ack()` explicitly:

```typescript
// CORRECT pattern (not used in v2.4.1)
for (const message of batch.messages) {
  try {
    const job = NotificationJobSchema.parse(message.body);
    await processNotification(job, env);
    message.ack();
  } catch (err) {
    console.error("Failed to process notification", { messageId: message.id, err });
    // Explicit per-message retry with delay; does NOT abort other messages
    message.retry({ delaySeconds: 60 });
  }
}
```

## Impact

- **Duration:** 2 hours 15 minutes of delayed delivery (07:16 – 09:30 UTC)
- **Messages affected:** ~38,000 notification jobs delayed; 0 permanently lost (DLQ replay recovered all)
- **User experience:** Push notifications and email digests delayed; no in-app feed impact
- **Near miss:** Within 5,000 messages of DLQ capacity limit — overflow would have caused permanent silent drops
- **Third-party API calls:** ~4,200 retry calls to Expo and Resend during DLQ replay; within rate limits

## Fix

```typescript
// workers/notification-consumer.ts — FIXED VERSION (v2.4.2)

const NotificationJobV1Schema = z.object({
  userId: z.string(),
  type: z.enum(["push", "email", "badge"]),
  payload: z.object({
    title: z.string(),
    body: z.string(),
    templateVersion: z.string().optional().default("v1"), // ← optional with default
  }),
  createdAt: z.number(),
});

// Schema version union for forward/backward compatibility
const NotificationJobSchema = z.union([
  NotificationJobV1Schema,
  // Future versions added here
]);

export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    const results = await Promise.allSettled(
      batch.messages.map(async (message) => {
        try {
          const parsed = NotificationJobSchema.safeParse(message.body);
          if (!parsed.success) {
            // Schema mismatch: log and send to DLQ immediately (no infinite retry)
            console.error("Schema validation failed", {
              messageId: message.id,
              errors: parsed.error.flatten(),
              body: JSON.stringify(message.body),
            });
            // ack() to remove from queue — send to manual review via Analytics Engine
            await logToAnalyticsEngine(env, "schema_mismatch", message.body);
            message.ack();
            return;
          }

          await processNotification(parsed.data, env);
          message.ack();
        } catch (err) {
          console.error("Notification processing error", { messageId: message.id, err });
          // Exponential backoff: each retry doubles delay (Cloudflare applies this automatically
          // based on retry count, but we can request a minimum delay)
          message.retry({ delaySeconds: Math.min(300, 30 * (message.attempts ?? 1)) });
        }
      })
    );

    const failures = results.filter((r) => r.status === "rejected");
    if (failures.length > 0) {
      console.warn(`${failures.length}/${batch.messages.length} messages failed in batch`);
    }
  },
};
```

```toml
# wrangler.toml — DLQ and retry configuration
[[queues.consumers]]
queue = "example project-notifications"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3           # After 3 retries, route to DLQ
dead_letter_queue = "example project-notifications-dlq"

[[queues.consumers]]
queue = "example project-notifications-dlq"
max_batch_size = 5
max_batch_timeout = 10
max_retries = 1           # DLQ consumer gets one attempt, then drops
```

## Prevention

1. **Schema migration policy:** consumer schema changes must be backward-compatible for at least one deploy cycle. New required fields must be optional-with-default in the consumer before the producer starts sending them.

2. **DLQ depth alert** added:
```typescript
// workers/dlq-monitor.ts — scheduled Worker
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const depth = await env.DLQ_DEPTH_KV.get("example project-notifications-dlq");
    if (Number(depth) > 10_000) {
      await alertPagerDuty(env, `DLQ depth ${depth} — approaching overflow`);
    }
  },
};
```

3. **Consumer smoke test** added to CI: deploys to staging and enqueues one valid + one invalid message, asserting the valid one is acked and the invalid one is not retried infinitely.

4. **Zod schema version registry** (`lib/schemas/notification-job.ts`) with explicit version constants; consumer accepts all known versions.

5. **DLQ replay runbook** documented and tested quarterly.

## Anti-patterns

- Letting a single message's exception abort the entire batch processing loop.
- Using `parse()` (throws) instead of `safeParse()` (returns result) inside batch consumers.
- Adding required fields to consumer schemas before the producer is updated to send them.
- Not monitoring DLQ depth — it silently fills up and overflows.
- Using the same queue for both high-priority and low-priority jobs (a crash loop blocks everything).
- Setting `max_retries` without understanding what happens when it is exhausted (DLQ routing vs. drop).

## Gotchas

- Cloudflare Queues does not expose DLQ depth via a standard API — must be tracked via a counter in KV or Analytics Engine, updated by the DLQ consumer itself.
- When a batch consumer throws without explicitly acking/retrying individual messages, Cloudflare retries the **entire batch** as a unit. This can cause already-processed messages to be re-processed — consumers must be idempotent.
- `message.retry({ delaySeconds })` only sets the delay for that specific message; other messages in the batch are unaffected.
- The DLQ is itself a Cloudflare Queue — it can also fill up. There is no automatic escalation path beyond the DLQ.
- `max_retries` counts the number of delivery attempts, not failures. A message that is acked on attempt 3 does not go to the DLQ.
- Cloudflare's retry delay doubles automatically with each attempt (exponential backoff), but the base delay and cap are not configurable via `wrangler.toml` as of 2026 — use `message.retry({ delaySeconds })` to override.

## Verification

```bash
# Replay DLQ manually
wrangler queues consumer dlq replay example project-notifications-dlq \
  --destination-queue example project-notifications \
  --max-messages 1000

# Confirm DLQ depth via KV counter
wrangler kv key get --namespace-id=<DLQ_MONITOR_NS_ID> "example project-notifications-dlq:depth"
# Expected: 0 after replay
```

Monitor `notification_delivery_success_rate` in Analytics Engine for 24 hours post-incident; confirm > 99.5%.

## Related

- `cloudflare-queues-duplicate-delivery-incident.md`
- `queues-consumer-scaling-backpressure-lesson.md`
- `queues-consumer-visibility-timeout-retry-storm-postmortem.md`
- `queue-consumers-must-be-idempotent.md`
- `queue-backlog-death-spirals.md`
- `retry-storm-queue-poison-message.md`

## Sources

- https://developers.cloudflare.com/queues/reference/batching-retries-dlq/
- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- https://developers.cloudflare.com/queues/platform/limits/
- https://developers.cloudflare.com/queues/examples/handle-failed-messages/
- https://zod.dev/
