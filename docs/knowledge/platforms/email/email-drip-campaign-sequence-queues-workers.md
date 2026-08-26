# Email Drip Campaign Sequence With Queues and Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
An anonymous social platform like example project (example.com) needs to send onboarding emails in a time-spaced sequence: welcome at signup, feature highlight at day 2, engagement nudge at day 5, and re-activation at day 14. Sending all emails synchronously at signup is wrong; a delayed queue-based architecture is required so each step fires at the right offset without blocking the API.

## Context
Cloudflare Queues supports delayed delivery via `delaySeconds`, making it a natural fit for drip sequences. A single Workers producer enqueues all steps at once with calculated delays; consumer Workers handle each step independently. D1 tracks which steps have been sent to allow idempotent retries and sequence cancellation when a user converts or unsubscribes.

## Sequence Design — Producer Worker

The producer runs once at signup. It calculates delay offsets for each drip step and publishes all messages to the same queue with `delaySeconds` populated. Each message carries enough context (userId, step, templateId) for the consumer to act without further lookups at enqueue time.

```typescript
// producer.ts — called from signup API route
interface Drip {
  step: number;
  templateId: string;
  delaySeconds: number;
}

const DRIP_SEQUENCE: Drip[] = [
  { step: 1, templateId: "onboarding-welcome",  delaySeconds: 0 },
  { step: 2, templateId: "onboarding-features", delaySeconds: 2 * 86400 },
  { step: 3, templateId: "onboarding-engage",   delaySeconds: 5 * 86400 },
  { step: 4, templateId: "onboarding-reactivate", delaySeconds: 14 * 86400 },
];

export async function enqueueOnboardingDrip(
  env: Env,
  userId: string,
  email: string
): Promise<void> {
  for (const drip of DRIP_SEQUENCE) {
    await env.EMAIL_QUEUE.send(
      {
        type: "drip",
        userId,
        email,
        step: drip.step,
        templateId: drip.templateId,
      },
      { delaySeconds: drip.delaySeconds }
    );
  }
}
```

## Step Tracking — D1 Schema and Guard

Before sending, the consumer checks D1 to confirm the step has not already been sent and the user has not unsubscribed. This prevents duplicate sends on queue retries and honours mid-sequence opt-outs.

```typescript
// migrations/0001_drip_steps.sql
/*
CREATE TABLE drip_steps (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id     TEXT NOT NULL,
  step        INTEGER NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | skipped
  sent_at     INTEGER,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  UNIQUE(user_id, step)
);

CREATE INDEX idx_drip_steps_user ON drip_steps(user_id);
*/

// consumer-guard.ts
export async function shouldSendStep(
  db: D1Database,
  userId: string,
  step: number
): Promise<boolean> {
  const existing = await db
    .prepare("SELECT status FROM drip_steps WHERE user_id = ?1 AND step = ?2")
    .bind(userId, step)
    .first<{ status: string }>();

  if (existing?.status === "sent") return false;

  // Check suppression / unsubscribe
  const suppressed = await db
    .prepare("SELECT 1 FROM suppressions WHERE user_id = ?1")
    .bind(userId)
    .first();

  return !suppressed;
}

export async function markStepSent(
  db: D1Database,
  userId: string,
  step: number
): Promise<void> {
  await db
    .prepare(`
      INSERT INTO drip_steps (user_id, step, status, sent_at)
      VALUES (?1, ?2, 'sent', unixepoch())
      ON CONFLICT (user_id, step) DO UPDATE SET status = 'sent', sent_at = unixepoch()
    `)
    .bind(userId, step)
    .run();
}
```

## Consumer Worker — Sending the Step

The consumer receives each queue message, runs the guard, renders the template, and calls the ESP. On send failure it throws so Cloudflare Queues retries with backoff; on guard rejection it acks the message silently (no retry needed).

```typescript
// consumer.ts
export default {
  async queue(batch: MessageBatch<DripMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { userId, email, step, templateId } = msg.body;

      try {
        const go = await shouldSendStep(env.DB, userId, step);
        if (!go) {
          msg.ack();
          continue;
        }

        const user = await env.DB
          .prepare("SELECT display_name FROM users WHERE id = ?1")
          .bind(userId)
          .first<{ display_name: string }>();

        const html = await renderTemplate(env, templateId, {
          displayName: user?.display_name ?? "there",
          unsubscribeUrl: `https://example.com/unsub?uid=${userId}`,
        });

        await sendViaMailChannels(env, {
          to: email,
          subject: SUBJECTS[templateId],
          html,
        });

        await markStepSent(env.DB, userId, step);
        msg.ack();
      } catch (err) {
        // Let Queues retry — do NOT ack
        console.error(`Drip step ${step} failed for ${userId}:`, err);
        msg.retry({ delaySeconds: 300 });
      }
    }
  },
};
```

## Sequence Cancellation

When a user converts (e.g. becomes an active poster) or unsubscribes, future drip steps must be skipped. Since Queues messages cannot be recalled, the correct approach is to insert a suppression row that the consumer guard reads. Pending messages will be received but immediately acked as skipped.

```typescript
// cancel-drip.ts
export async function cancelDripForUser(
  db: D1Database,
  userId: string
): Promise<void> {
  // Mark all pending steps as skipped
  await db
    .prepare(`
      UPDATE drip_steps
      SET status = 'skipped'
      WHERE user_id = ?1 AND status = 'pending'
    `)
    .bind(userId)
    .run();

  // Insert suppression so consumer guard short-circuits
  await db
    .prepare(`
      INSERT OR IGNORE INTO suppressions (user_id, reason, created_at)
      VALUES (?1, 'drip_cancelled', unixepoch())
    `)
    .bind(userId)
    .run();
}
```

## Anti-patterns
- Enqueuing each step only after the previous one completes — this couples steps, breaks retries, and loses the sequence if a consumer fails.
- Using a cron Worker that polls D1 for "emails due now" — works at small scale but becomes a hot query at volume; Queues delay is purpose-built for this.
- Storing template HTML in the queue message — messages have a 128 KB limit and template data belongs in R2 or KV, not the message body.
- Cancelling a drip by querying and deleting queue messages — the Queues API does not support message deletion; use the guard pattern instead.

## Gotchas
- `delaySeconds` has a maximum of 12 hours (43200 s) on the free plan; paid plan allows up to 12 hours as well — for multi-day delays you must re-enqueue from the consumer or chain through a scheduled Cron Trigger.
- Queue retries count against the `maxRetries` setting (default 3); configure `deadLetterQueue` to capture permanently failed steps for manual investigation.
- D1 `ON CONFLICT DO UPDATE` requires the conflicting column to be in a `UNIQUE` constraint — ensure the migration creates `UNIQUE(user_id, step)`.
- MailChannels rate limits apply per sending domain; add per-user rate limiting at the consumer to avoid bursting when many users enter a drip simultaneously.

## Verification
1. Sign up a test user and confirm 4 messages appear in the queue dashboard with correct delay offsets.
2. Advance system time (or use a very short delay in staging) and verify each step arrives in D1 `drip_steps` with `status = 'sent'`.
3. Unsubscribe the user after step 1 and confirm steps 2–4 land with `status = 'skipped'`.
4. Trigger a consumer failure and verify the message retries with the configured delay.

## Related
- [email-digest-batching-queues-d1-workers.md](email-digest-batching-queues-d1-workers.md)
- [email-suppression-list-kv-workers.md](email-suppression-list-kv-workers.md)
- [transactional-queue-cloudflare-queues.md](transactional-queue-cloudflare-queues.md)
- [email-retry-exponential-backoff.md](email-retry-exponential-backoff.md)
- [drip-campaign-architecture.md](drip-campaign-architecture.md)

## Sources
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/reference/delayed-messages/
- https://developers.cloudflare.com/queues/reference/dead-letter-queues/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/email-routing/email-workers/
