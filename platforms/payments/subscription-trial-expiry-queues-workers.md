# Subscription Trial Period Expiry Scheduling with Cloudflare Queues

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You run your own subscription engine (or supplement Stripe Billing) and need to send trial-ending reminders, switch trial users to paid plans, and cancel non-converting trials — all at precise times. Cron Triggers fire at fixed intervals and must scan the entire trials table; Cloudflare Queues with delayed delivery lets you schedule work at enrollment time and fire exactly when the trial ends, with no polling scan required.

## Context

Cloudflare Queues support `delaySeconds` on individual messages (up to 42,950,400 seconds / ~497 days). A message published at trial signup with `delaySeconds` equal to the remaining trial duration will be delivered to a consumer Worker exactly when the trial ends. D1 stores the canonical trial state; the Queue drives timely execution. This pattern decouples scheduling from polling and survives Worker restarts.

---

## Infrastructure (wrangler.toml)

```toml
[[queues.producers]]
binding = "TRIAL_QUEUE"
queue   = "subscription-trial-events"

[[queues.consumers]]
queue            = "subscription-trial-events"
max_batch_size   = 10
max_batch_timeout = 30
max_retries      = 3
dead_letter_queue = "subscription-trial-dlq"

[[d1_databases]]
binding     = "DB"
database_name = "subscriptions"
database_id   = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## D1 Schema

```sql
-- migrations/0001_trials.sql
CREATE TABLE IF NOT EXISTS trials (
  id           TEXT PRIMARY KEY,            -- UUID
  user_id      TEXT NOT NULL,
  plan_id      TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'trialing', -- trialing | converted | cancelled | expired
  starts_at    INTEGER NOT NULL,            -- Unix ms
  ends_at      INTEGER NOT NULL,            -- Unix ms
  payment_method_id TEXT,                  -- Stripe PM id (null = no card on file)
  created_at   INTEGER NOT NULL DEFAULT (unixepoch('now') * 1000)
);
CREATE INDEX IF NOT EXISTS idx_trials_user   ON trials(user_id);
CREATE INDEX IF NOT EXISTS idx_trials_status ON trials(status);
```

## Enqueue on Trial Start

```typescript
// src/handlers/start-trial.ts
import { nanoid } from "nanoid";

interface Env {
  DB: D1Database;
  TRIAL_QUEUE: Queue<TrialExpiryMessage>;
}

interface TrialExpiryMessage {
  type: "TRIAL_REMINDER_48H" | "TRIAL_EXPIRED";
  trialId: string;
  userId: string;
}

export async function startTrial(
  env: Env,
  userId: string,
  planId: string,
  trialDays: number,
  paymentMethodId?: string
): Promise<string> {
  const trialId    = nanoid();
  const startsAt   = Date.now();
  const endsAt     = startsAt + trialDays * 86_400_000;
  const endsAtSec  = Math.floor(endsAt / 1000);
  const nowSec     = Math.floor(startsAt / 1000);

  // 1. Persist trial record
  await env.DB.prepare(
    `INSERT INTO trials (id, user_id, plan_id, starts_at, ends_at, payment_method_id)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(trialId, userId, planId, startsAt, endsAt, paymentMethodId ?? null).run();

  // 2. Enqueue 48-hour reminder
  const reminderDelay = endsAtSec - nowSec - 48 * 3600;
  if (reminderDelay > 0) {
    await env.TRIAL_QUEUE.send(
      { type: "TRIAL_REMINDER_48H", trialId, userId },
      { delaySeconds: reminderDelay }
    );
  }

  // 3. Enqueue expiry event at trial end
  await env.TRIAL_QUEUE.send(
    { type: "TRIAL_EXPIRED", trialId, userId },
    { delaySeconds: endsAtSec - nowSec }
  );

  return trialId;
}
```

## Queue Consumer: Process Expiry Events

```typescript
// src/consumers/trial-expiry.ts
import Stripe from "stripe";

interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  TRIAL_QUEUE: Queue<TrialExpiryMessage>;
}

export default {
  async queue(
    batch: MessageBatch<TrialExpiryMessage>,
    env: Env
  ): Promise<void> {
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: "2024-06-20" });

    for (const msg of batch.messages) {
      try {
        await handleMessage(env, stripe, msg.body);
        msg.ack();
      } catch (err) {
        console.error("trial-expiry failed", msg.body, err);
        msg.retry();
      }
    }
  },
};

async function handleMessage(
  env: Env,
  stripe: Stripe,
  msg: TrialExpiryMessage
): Promise<void> {
  const trial = await env.DB.prepare(
    "SELECT * FROM trials WHERE id = ?"
  ).bind(msg.trialId).first<{
    id: string; user_id: string; plan_id: string;
    status: string; payment_method_id: string | null;
  }>();

  if (!trial || trial.status !== "trialing") return; // already converted/cancelled

  if (msg.type === "TRIAL_REMINDER_48H") {
    await sendReminderEmail(trial.user_id, trial.plan_id);
    return;
  }

  // TRIAL_EXPIRED path
  if (trial.payment_method_id) {
    // Attempt to convert — create Stripe subscription
    await convertToSubscription(env, stripe, trial);
  } else {
    // No payment method — cancel
    await env.DB.prepare(
      "UPDATE trials SET status = 'expired' WHERE id = ? AND status = 'trialing'"
    ).bind(trial.id).run();
    await sendExpiredEmail(trial.user_id);
  }
}

async function convertToSubscription(
  env: Env,
  stripe: Stripe,
  trial: { id: string; user_id: string; plan_id: string; payment_method_id: string }
): Promise<void> {
  const sub = await stripe.subscriptions.create({
    customer:              trial.user_id, // assumes user_id == Stripe customer id
    default_payment_method: trial.payment_method_id,
    items: [{ price: trial.plan_id }],
    metadata: { trial_id: trial.id },
  });

  const converted = sub.status === "active";
  await env.DB.prepare(
    "UPDATE trials SET status = ? WHERE id = ? AND status = 'trialing'"
  ).bind(converted ? "converted" : "expired", trial.id).run();
}

async function sendReminderEmail(userId: string, planId: string): Promise<void> {
  // integrate with your email provider
  console.log(`reminder email → user=${userId} plan=${planId}`);
}

async function sendExpiredEmail(userId: string): Promise<void> {
  console.log(`expired email → user=${userId}`);
}
```

## Dead-Letter Queue Monitoring

```typescript
// src/consumers/trial-dlq.ts — alert on unprocessable messages
export default {
  async queue(
    batch: MessageBatch<TrialExpiryMessage>,
    _env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      console.error("TRIAL DLQ — unprocessable after retries:", JSON.stringify(msg.body));
      // page on-call or write to analytics
      msg.ack();
    }
  },
};
```

## Extending a Trial Without Re-enqueuing

```typescript
// Re-enqueue only the expiry event after extending the trial.
// The old message will be processed but ignored (trial.status check).
export async function extendTrial(
  env: Env,
  trialId: string,
  extraDays: number
): Promise<void> {
  const result = await env.DB.prepare(
    `UPDATE trials
        SET ends_at = ends_at + ?
      WHERE id = ? AND status = 'trialing'
   RETURNING ends_at`
  ).bind(extraDays * 86_400_000, trialId).first<{ ends_at: number }>();

  if (!result) return;

  const newDelaySec = Math.max(
    1,
    Math.floor((result.ends_at - Date.now()) / 1000)
  );

  await env.TRIAL_QUEUE.send(
    { type: "TRIAL_EXPIRED", trialId, userId: "" }, // userId fetched in consumer
    { delaySeconds: newDelaySec }
  );
}
```

---

## Anti-patterns

- Relying solely on Stripe's `trial_end` webhook for conversion — Stripe webhooks can be delayed; a duplicate check against your D1 state is safer.
- Using a Cron Trigger with `SELECT * FROM trials WHERE ends_at < ?` on millions of rows — this scans the full table every minute; the Queue approach scales to arbitrary trial volumes.
- Not acknowledging messages on success — un-acked messages retry after `visibilityTimeoutSeconds`, causing double-conversion.
- Setting `delaySeconds` to a negative value for trials that have already expired at enqueue time — clamp to 1.

## Gotchas

- Queues `delaySeconds` is approximate — consumer delivery can be up to ~30 s late; this is acceptable for trial expiry but not for real-time authorization.
- The old expiry message for an extended trial will still be delivered; the D1 status guard (`trial.status !== 'trialing'`) makes it a no-op.
- A Worker retry after a crash may re-run `convertToSubscription` — use Stripe's `metadata.trial_id` to detect duplicate subscriptions.
- `max_batch_size` of 1 makes error isolation easier (one failed conversion doesn't block others), but reduces throughput; keep at 10 and handle errors per-message.

## Verification

```bash
# Publish a test message with a 5-second delay
wrangler queues send subscription-trial-events \
  '{"type":"TRIAL_EXPIRED","trialId":"test-123","userId":"usr_test"}' \
  --delay-seconds 5

# Tail consumer logs
wrangler tail --format=pretty
```

## Related

- `stripe-trial-periods.md`
- `stripe-subscription-trial-abuse-prevention-workers.md`
- `payment-dunning-management-cloudflare-queues.md`
- `payment-retry-exponential-backoff-cloudflare-queues.md`
- `subscription-billing-lifecycle.md`

## Sources

- https://developers.cloudflare.com/queues/configuration/batching-retries/
- https://developers.cloudflare.com/queues/reference/delay-messages/
- https://docs.stripe.com/billing/subscriptions/trials
