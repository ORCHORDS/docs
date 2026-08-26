# Subscription Dunning Workflow Using Workers + Queues + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A subscription renewal charge fails. Instead of immediately cancelling the subscription, you need a dunning workflow: send reminder emails over several days, retry the charge on a schedule, and only suspend the subscription after the grace period expires. A win-back flow should re-activate the subscription once a valid payment method is added.

## Context

Dunning (from Old English *dunn*, to demand payment) is the systematic process of communicating with subscribers to collect overdue payments. A well-designed dunning workflow recovers 10–40 % of failed renewals before they churn.

This implementation uses:
- **Cloudflare Queues** for the delayed email and retry schedule.
- **D1** for subscription and dunning state.
- **MailChannels** for transactional email (available natively from Workers).
- **Stripe webhooks** as the trigger for dunning entry.

## Solution

### 1. Data Model

```sql
-- migrations/004_dunning.sql
CREATE TABLE IF NOT EXISTS subscriptions (
  id                TEXT PRIMARY KEY,
  customer_id       TEXT NOT NULL,
  customer_email    TEXT NOT NULL,
  plan_id           TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'active',
    -- active | past_due | suspended | cancelled | win_back
  current_period_end TEXT NOT NULL,
  grace_period_end   TEXT,
  payment_method_id  TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dunning_state (
  subscription_id   TEXT PRIMARY KEY REFERENCES subscriptions(id),
  dunning_started_at TEXT NOT NULL,
  last_email_sent_at TEXT,
  emails_sent       INTEGER NOT NULL DEFAULT 0,
  last_retry_at     TEXT,
  retries_attempted INTEGER NOT NULL DEFAULT 0,
  final_error_code  TEXT,
  resolved_at       TEXT,
  resolution        TEXT  -- 'paid' | 'suspended' | 'cancelled'
);

CREATE TABLE IF NOT EXISTS dunning_events (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subscription_id TEXT NOT NULL REFERENCES subscriptions(id),
  event_type      TEXT NOT NULL,
    -- email_sent | charge_attempted | charge_succeeded |
    -- charge_failed | suspended | win_back_triggered
  metadata        TEXT,  -- JSON blob
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_dunning_events_sub ON dunning_events (subscription_id, created_at);
```

### 2. Type Definitions

```typescript
// src/types/dunning.ts
export interface DunningJob {
  subscriptionId: string;
  customerId: string;
  customerEmail: string;
  planId: string;
  step: DunningStep;
  dunningStartedAt: string;
  paymentMethodId: string | null;
}

export type DunningStep =
  | 'email_day_0'
  | 'retry_day_1'
  | 'email_day_3'
  | 'retry_day_4'
  | 'email_day_6'
  | 'retry_day_7'
  | 'suspend';

export const DUNNING_SCHEDULE: Record<DunningStep, {
  nextStep: DunningStep | null;
  delaySeconds: number;
  action: 'email' | 'retry' | 'suspend';
}> = {
  email_day_0: { nextStep: 'retry_day_1',  delaySeconds: 86400,  action: 'email' },
  retry_day_1: { nextStep: 'email_day_3',  delaySeconds: 172800, action: 'retry' },
  email_day_3: { nextStep: 'retry_day_4',  delaySeconds: 86400,  action: 'email' },
  retry_day_4: { nextStep: 'email_day_6',  delaySeconds: 172800, action: 'retry' },
  email_day_6: { nextStep: 'retry_day_7',  delaySeconds: 86400,  action: 'email' },
  retry_day_7: { nextStep: 'suspend',      delaySeconds: 3600,   action: 'retry' },
  suspend:     { nextStep: null,           delaySeconds: 0,      action: 'suspend' },
};
```

### 3. Dunning Entry Point (Stripe Webhook)

```typescript
// src/handlers/dunning/entry.ts
import Stripe from 'stripe';
import { Env } from '../../types';
import { DunningJob } from '../../types/dunning';

export async function handleInvoicePaymentFailed(
  event: Stripe.Event,
  env: Env
): Promise<void> {
  const invoice = event.data.object as Stripe.Invoice;
  const subscriptionId = invoice.subscription as string;
  if (!subscriptionId) return;

  // Fetch subscription details from D1
  const sub = await env.DB
    .prepare('SELECT * FROM subscriptions WHERE id = ?')
    .bind(subscriptionId)
    .first<{ customer_email: string; plan_id: string;
              payment_method_id: string | null; status: string }>();

  if (!sub || sub.status === 'suspended' || sub.status === 'cancelled') return;

  const now = new Date().toISOString();

  // Set subscription to past_due and record grace period
  const gracePeriodEnd = new Date(
    Date.now() + 7 * 24 * 60 * 60 * 1000
  ).toISOString();

  await env.DB.batch([
    env.DB.prepare(`
      UPDATE subscriptions
      SET status = 'past_due', grace_period_end = ?, updated_at = ?
      WHERE id = ?
    `).bind(gracePeriodEnd, now, subscriptionId),

    env.DB.prepare(`
      INSERT INTO dunning_state (subscription_id, dunning_started_at)
      VALUES (?, ?)
      ON CONFLICT (subscription_id) DO UPDATE SET
        dunning_started_at = ?, last_email_sent_at = NULL,
        emails_sent = 0, retries_attempted = 0, resolved_at = NULL
    `).bind(subscriptionId, now, now),
  ]);

  const job: DunningJob = {
    subscriptionId,
    customerId: invoice.customer as string,
    customerEmail: sub.customer_email,
    planId: sub.plan_id,
    step: 'email_day_0',
    dunningStartedAt: now,
    paymentMethodId: sub.payment_method_id,
  };

  // Fire the first dunning step immediately
  await env.DUNNING_QUEUE.send(job, { contentType: 'json' });
}
```

### 4. Dunning Queue Consumer

```typescript
// src/handlers/dunning/consumer.ts
import { Env } from '../../types';
import { DunningJob, DUNNING_SCHEDULE } from '../../types/dunning';
import { sendDunningEmail } from '../../services/email';
import { retrySubscriptionCharge } from '../../services/stripe';

export async function dunningQueueHandler(
  batch: MessageBatch<DunningJob>,
  env: Env
): Promise<void> {
  for (const message of batch.messages) {
    const job = message.body;
    const schedule = DUNNING_SCHEDULE[job.step];

    try {
      // Check if subscription is still in dunning
      const sub = await env.DB
        .prepare(`SELECT status FROM subscriptions WHERE id = ?`)
        .bind(job.subscriptionId)
        .first<{ status: string }>();

      if (!sub || !['past_due'].includes(sub.status)) {
        // Already resolved or cancelled — bail out
        message.ack();
        continue;
      }

      switch (schedule.action) {
        case 'email':
          await sendDunningEmail(env, job);
          await recordDunningEvent(env, job.subscriptionId, 'email_sent', {
            step: job.step,
          });
          break;

        case 'retry': {
          const result = await retrySubscriptionCharge(env, job);
          if (result.succeeded) {
            await resolveDunning(env, job.subscriptionId, 'paid');
            message.ack();
            continue;
          }
          await recordDunningEvent(env, job.subscriptionId, 'charge_failed', {
            step: job.step, errorCode: result.errorCode,
          });
          break;
        }

        case 'suspend':
          await suspendSubscription(env, job.subscriptionId);
          await recordDunningEvent(env, job.subscriptionId, 'suspended', {});
          message.ack();
          continue;
      }

      // Schedule next step
      if (schedule.nextStep) {
        const nextJob: DunningJob = { ...job, step: schedule.nextStep };
        await env.DUNNING_QUEUE.send(nextJob, {
          delaySeconds: schedule.delaySeconds,
          contentType: 'json',
        });
      }

      message.ack();
    } catch (err) {
      console.error(`Dunning step ${job.step} failed for ${job.subscriptionId}:`, err);
      message.retry({ delaySeconds: 300 });
    }
  }
}

async function suspendSubscription(
  env: Env,
  subscriptionId: string
): Promise<void> {
  await env.DB.prepare(`
    UPDATE subscriptions
    SET status = 'suspended', updated_at = datetime('now')
    WHERE id = ?
  `).bind(subscriptionId).run();
}

async function resolveDunning(
  env: Env,
  subscriptionId: string,
  resolution: 'paid' | 'suspended'
): Promise<void> {
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(`
      UPDATE dunning_state
      SET resolved_at = ?, resolution = ?
      WHERE subscription_id = ?
    `).bind(now, resolution, subscriptionId),
    env.DB.prepare(`
      UPDATE subscriptions
      SET status = ?, grace_period_end = NULL, updated_at = ?
      WHERE id = ?
    `).bind(resolution === 'paid' ? 'active' : 'suspended', now, subscriptionId),
  ]);
}

async function recordDunningEvent(
  env: Env,
  subscriptionId: string,
  eventType: string,
  metadata: Record<string, unknown>
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO dunning_events (subscription_id, event_type, metadata)
    VALUES (?, ?, ?)
  `).bind(subscriptionId, eventType, JSON.stringify(metadata)).run();
}
```

### 5. MailChannels Email Sender

```typescript
// src/services/email.ts
import { Env } from '../types';
import { DunningJob, DunningStep } from '../types/dunning';

const EMAIL_SUBJECTS: Record<string, string> = {
  email_day_0: 'Action required: your payment failed',
  email_day_3: 'Reminder: please update your payment method',
  email_day_6: 'Final notice: your subscription will be suspended tomorrow',
};

export async function sendDunningEmail(
  env: Env,
  job: DunningJob
): Promise<void> {
  const subject = EMAIL_SUBJECTS[job.step] ?? 'Payment issue with your subscription';

  const payload = {
    personalizations: [{
      to: [{ email: job.customerEmail }],
    }],
    from: { email: env.FROM_EMAIL, name: env.FROM_NAME },
    subject,
    content: [{
      type: 'text/html',
      value: buildEmailHtml(job, subject),
    }],
  };

  const response = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok && response.status !== 202) {
    throw new Error(`MailChannels send failed: ${response.status}`);
  }

  await env.DB.prepare(`
    UPDATE dunning_state
    SET emails_sent = emails_sent + 1, last_email_sent_at = datetime('now')
    WHERE subscription_id = ?
  `).bind(job.subscriptionId).run();
}

function buildEmailHtml(job: DunningJob, subject: string): string {
  const updateUrl = `${process.env.BASE_URL}/billing/update?sub=${job.subscriptionId}`;
  return `
    <h2>${subject}</h2>
    <p>We were unable to charge your subscription for plan <strong>${job.planId}</strong>.</p>
    <p>Please update your payment method to avoid service interruption:</p>
    <a  style="background:#6366f1;color:#fff;padding:12px 24px;
      border-radius:6px;text-decoration:none;">Update Payment Method</a>
    <p>If you have questions, reply to this email.</p>
  `;
}
```

### 6. Win-Back Flow

```typescript
// src/handlers/dunning/winback.ts
// Triggered when a suspended subscriber adds a new payment method
import { Env } from '../../types';

export async function handleWinBack(
  request: Request,
  env: Env
): Promise<Response> {
  const { subscriptionId, newPaymentMethodId } =
    await request.json() as { subscriptionId: string; newPaymentMethodId: string };

  const sub = await env.DB
    .prepare('SELECT * FROM subscriptions WHERE id = ?')
    .bind(subscriptionId)
    .first<{ status: string; plan_id: string; customer_id: string }>();

  if (!sub || sub.status !== 'suspended') {
    return new Response('Subscription not eligible for win-back', { status: 400 });
  }

  // Update payment method and set status to win_back
  await env.DB.prepare(`
    UPDATE subscriptions
    SET payment_method_id = ?, status = 'win_back', updated_at = datetime('now')
    WHERE id = ?
  `).bind(newPaymentMethodId, subscriptionId).run();

  // Re-enqueue an immediate charge attempt
  await env.DUNNING_QUEUE.send(
    {
      subscriptionId,
      customerId: sub.customer_id,
      customerEmail: '',  // not needed for charge-only step
      planId: sub.plan_id,
      step: 'retry_day_1',
      dunningStartedAt: new Date().toISOString(),
      paymentMethodId: newPaymentMethodId,
    },
    { delaySeconds: 0, contentType: 'json' }
  );

  return new Response(JSON.stringify({ status: 'win_back_triggered' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

### 7. Dunning Metrics Query

```sql
-- Daily dunning report
SELECT
  date(dunning_started_at)  AS cohort_date,
  COUNT(*)                  AS entered_dunning,
  SUM(resolution = 'paid')  AS recovered,
  ROUND(100.0 * SUM(resolution = 'paid') / COUNT(*), 1) AS recovery_rate_pct,
  AVG(emails_sent)          AS avg_emails_sent,
  AVG(retries_attempted)    AS avg_retries
FROM dunning_state
GROUP BY date(dunning_started_at)
ORDER BY cohort_date DESC
LIMIT 30;
```

## Implementation Details

**Grace period tracking**: `grace_period_end` on the subscription row is the human-readable deadline. The dunning schedule drives the actual workflow — the `suspend` step fires on day 7 regardless of what `grace_period_end` says. Keep both in sync.

**Idempotent email sends**: MailChannels returns 202 on success. If the Worker crashes after sending but before acking, the message is re-delivered and the email is re-sent. Add a deduplication check in `sendDunningEmail` by querying `dunning_events` for a matching step before sending.

**Multiple failed methods**: `paymentMethodId` is the last known method. If the customer has multiple methods on file, iterate them before marking a retry as failed.

## Anti-patterns

- **Sending every email in a single Worker invocation**: A timeout kills the batch. Use the queue to fan out each email as a separate message.
- **Hard-coding email delays in Worker code**: The `DUNNING_SCHEDULE` map externalises delays, making them easy to adjust without deployment.
- **Not recording dunning events**: Without an audit trail you cannot compute recovery rates or debug why a subscription was suspended.
- **Retrying with the same declined card immediately**: A card declined for `insufficient_funds` will fail again in 30 seconds. Space retries by at least 24 hours.

## Gotchas

- MailChannels is available from Workers without an API key for domains verified with Cloudflare. For non-Cloudflare domains, you need a MailChannels API key.
- Queues `delaySeconds` max is 43,200 (12 hours). Day-3 and Day-6 delays (172,800 s) require re-enqueuing with the max delay or using a Cron Trigger to re-enqueue.
- `D1Database.batch()` executes statements in order but rolls back all on failure — wrap multi-step state transitions in a batch.
- Stripe's `invoice.payment_failed` webhook can fire multiple times for the same invoice. Guard with `ON CONFLICT … DO UPDATE` and check the current `status` before entering dunning.

## Verification

```bash
# Simulate an invoice.payment_failed webhook
curl -X POST https://your-worker.workers.dev/webhooks/stripe \
  -H 'Content-Type: application/json' \
  -H 'stripe-signature: <sig>' \
  -d @test-fixtures/invoice-payment-failed.json

# Check dunning state
wrangler d1 execute payments \
  --command "SELECT * FROM dunning_state WHERE subscription_id='sub_test';"

# Recovery metrics
wrangler d1 execute payments \
  --command "
    SELECT cohort_date, recovery_rate_pct FROM (
      SELECT date(dunning_started_at) AS cohort_date,
        ROUND(100.0*SUM(resolution='paid')/COUNT(*),1) AS recovery_rate_pct
      FROM dunning_state GROUP BY 1
    ) ORDER BY cohort_date DESC LIMIT 7;"
```

## Related

- `documentation/categories/payments/workers-payment-retry-exponential-backoff.md`
- `documentation/categories/payments/workers-stripe-connect-oauth-flow.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://mailchannels.zendesk.com/hc/en-us/articles/4565898358413
- https://stripe.com/docs/billing/subscriptions/overview#subscription-lifecycle
- https://stripe.com/docs/billing/revenue-recovery
