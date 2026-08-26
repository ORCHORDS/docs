# R2 Event Notification Missed Fires Postmortem

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

An image processing pipeline depended on R2 event notifications to trigger a Worker
whenever a new file was uploaded to an R2 bucket. After a routine bucket policy update,
event notifications silently stopped firing for approximately 4 hours. No uploads failed
— objects were written to R2 successfully — but the downstream processing Worker never
received the Queue messages that notifications are routed through. Processed images were
not generated, thumbnails were missing, and no alert fired because the consumer queue
depth was never monitored.

## Context

Cloudflare R2 event notifications are delivered by routing bucket events through a
Cloudflare Queue. The bucket-to-queue binding is a configuration relationship: if the
queue binding is deleted, the queue is recreated under a different ID, or the bucket
event rule is removed, notifications stop silently. There is no dead-letter mechanism
for missed R2 event notifications — if a message is never enqueued the event is
permanently lost. Notifications are best-effort; Cloudflare does not guarantee exactly-
once or at-least-once delivery for the R2-to-Queue leg (the Queue-to-consumer leg does
guarantee at-least-once). Any architecture that requires guaranteed processing of every
R2 upload must have a reconciliation path that does not depend solely on event
notifications.

## Validate Notification Config After Infrastructure Changes

Any wrangler deploy or Terraform apply that touches a bucket or queue binding should
assert that the notification rule is still present.

```typescript
// scripts/validate-r2-notifications.ts
// Run as part of CI post-deploy validation
import { execSync } from 'node:child_process';

interface R2NotificationRule {
  queue: string;
  actions: string[];
}

function getNotificationRules(bucket: string): R2NotificationRule[] {
  const raw = execSync(
    `wrangler r2 bucket notification list ${bucket} --json`,
  ).toString();
  return JSON.parse(raw) as R2NotificationRule[];
}

function assertNotification(bucket: string, expectedQueue: string): void {
  const rules = getNotificationRules(bucket);
  const matched = rules.find((r) => r.queue === expectedQueue);
  if (!matched) {
    throw new Error(
      `R2 bucket '${bucket}' has no notification rule targeting queue '${expectedQueue}'`,
    );
  }
  if (!matched.actions.includes('PutObject')) {
    throw new Error(
      `Notification rule for '${bucket}' -> '${expectedQueue}' does not include PutObject`,
    );
  }
  console.log(`OK: ${bucket} -> ${expectedQueue} (${matched.actions.join(', ')})`);
}

assertNotification('media-uploads', 'image-processing-queue');
```

## Monitor Queue Consumer Depth as a Processing Health Signal

Because notifications are the only trigger for processing, a rising queue depth (messages
not being consumed) and a falling consumer invocation rate both indicate a notification
or consumer problem.

```typescript
// src/queue-health-worker.ts
// Companion cron Worker: checks consumer metrics via Analytics Engine
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const result = await env.DB.prepare(
      `SELECT SUM(messages_delivered) as delivered,
              SUM(messages_consumed) as consumed
       FROM analytics_engine_queue_metrics
       WHERE queue_name = 'image-processing-queue'
         AND timestamp > unixepoch() - 600`,
    ).first<{ delivered: number; consumed: number }>();

    if (!result) return;
    const lag = result.delivered - result.consumed;
    if (lag > 50) {
      await fetch(env.ALERT_WEBHOOK, {
        method: 'POST',
        body: JSON.stringify({ alert: 'queue_lag', lag, queue: 'image-processing-queue' }),
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

## Reconciliation Sweep for Missed Events

A periodic cron Worker reconciles processed vs uploaded objects by listing R2 keys and
comparing against a processed-state table in D1. Any unprocessed object triggers
re-queuing.

```typescript
// src/reconcile-worker.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(reconcile(env));
  },
} satisfies ExportedHandler<Env>;

async function reconcile(env: Env): Promise<void> {
  let cursor: string | undefined;
  do {
    const listed = await env.BUCKET.list({ limit: 100, cursor });
    cursor = listed.truncated ? listed.cursor : undefined;

    for (const obj of listed.objects) {
      const processed = await env.DB.prepare(
        'SELECT 1 FROM processed_objects WHERE r2_key = ?1',
      )
        .bind(obj.key)
        .first();
      if (!processed) {
        await env.QUEUE.send({ key: obj.key, etag: obj.etag });
      }
    }
  } while (cursor);
}
```

## Idempotent Consumer Handles Re-queued Events

Because the reconciliation sweep re-queues events for objects already in flight, the
consumer must be idempotent to avoid double-processing.

```typescript
// src/image-processor.ts
export default {
  async queue(batch: MessageBatch<{ key: string; etag: string }>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { key, etag } = msg.body;
      const existing = await env.DB.prepare(
        'SELECT etag FROM processed_objects WHERE r2_key = ?1',
      )
        .bind(key)
        .first<{ etag: string }>();

      if (existing?.etag === etag) {
        msg.ack(); // already processed this exact version
        continue;
      }

      await processImage(env, key);
      await env.DB.prepare(
        'INSERT INTO processed_objects (r2_key, etag, processed_at) VALUES (?1, ?2, unixepoch()) ON CONFLICT(r2_key) DO UPDATE SET etag = ?2, processed_at = unixepoch()',
      )
        .bind(key, etag)
        .run();
      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;

async function processImage(_env: Env, _key: string): Promise<void> {
  /* thumbnail generation logic */
}
```

## Dead-Letter Handling for Consumer Failures

While R2-to-Queue delivery is not guaranteed, Queue-to-consumer delivery is. Configure a
dead-letter queue so messages the consumer fails to process are retained for investigation.

```typescript
// wrangler.toml excerpt (TypeScript representation for documentation)
// [[queues.consumers]]
// queue = "image-processing-queue"
// dead_letter_queue = "image-processing-dlq"
// max_retries = 3
// max_concurrency = 5

export default {
  async queue(batch: MessageBatch<{ key: string; etag: string }>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processImage(env, msg.body.key);
        msg.ack();
      } catch (err) {
        console.error('processing failed', { key: msg.body.key, err });
        msg.retry(); // will route to DLQ after max_retries
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Treating R2 event notifications as a guaranteed delivery channel — they are best-effort
  on the bucket-to-queue leg.
- No reconciliation sweep — a 4-hour notification outage leaves 4 hours of data in a
  permanently unprocessed state.
- Mutating queue or bucket bindings without running a post-deploy validation check.
- No monitoring on queue consumer depth — a rising backlog is an early warning sign
  that consumers have stopped receiving events.

## Gotchas

- Recreating a Cloudflare Queue (delete + create) generates a new queue ID. Bucket
  notification rules reference the queue ID, not the name; the binding silently breaks.
- `wrangler r2 bucket notification list` requires the account to have the Queue binding
  still in wrangler.toml; if the binding is removed the command still shows the rule
  even though messages no longer flow.
- R2 event notifications do not fire for multipart upload parts — only for the
  `CompleteMultipartUpload` action (mapped to `PutObject` in notification rules).
- There is no replay or backfill mechanism for R2 notifications; once a notification
  window is missed, only a reconciliation sweep can recover those objects.

## Verification

1. Deploy the validation script in CI as a post-deploy step; confirm it fails with a
   meaningful error if the notification rule is removed manually.
2. Delete the queue binding and upload a test object; verify the monitoring cron fires an
   alert within 10 minutes.
3. Upload 500 objects without any notification rule active, then restore the rule and run
   the reconciliation sweep; verify all 500 objects appear in `processed_objects`.
4. Send a duplicate event for an already-processed key and confirm the consumer acks it
   without re-running `processImage`.

## Related

- `r2-presigned-url-race-condition-upload-incident.md`
- `r2-multipart-upload-size-limit-lesson.md`
- `queue-consumers-must-be-idempotent.md`
- `webhook-delivery-is-not-guaranteed.md`
- `cloudflare-queues-vs-traditional-message-queues.md`

## Sources

- Cloudflare R2 documentation — event notifications (2026)
- Cloudflare Queues documentation — delivery guarantees
- Internal postmortem: example.com image processing pipeline outage, Q2 2026
- Cloudflare Community: "R2 event notifications not firing after queue recreation" thread
