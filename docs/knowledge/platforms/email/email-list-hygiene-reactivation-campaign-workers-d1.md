# Email List Hygiene Reactivation Campaigns with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Open and click rates are declining. Gmail and Yahoo treat bulk sends to chronically inactive
addresses as a reputation signal. You need to identify dormant subscribers, run a structured
win-back sequence, and automatically suppress those who still do not engage — all without a
dedicated marketing automation platform.

## Context

Reactivation (win-back) campaigns serve two hygiene goals: recovering genuine subscribers who may
have missed emails, and cleanly sunsetting those who have permanently disengaged. Engagement state
and reactivation step are tracked in D1; Cloudflare Queues drive the step sequence; a cron job
identifies who enters the flow.

This article covers the full automated loop. See `re-engagement-campaign.md` for conceptual
strategy and `email-sunset-policy.md` for suppression rules.

---

## 1. D1 Schema

```sql
CREATE TABLE subscribers (
  id               TEXT PRIMARY KEY,
  email            TEXT NOT NULL UNIQUE,
  last_opened_at   TEXT,
  last_clicked_at  TEXT,
  subscribed_at    TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'active'
    CHECK(status IN ('active','reactivation','suppressed'))
);

CREATE TABLE reactivation_sequences (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  subscriber_id  TEXT NOT NULL REFERENCES subscribers(id),
  step           INTEGER NOT NULL DEFAULT 1,  -- 1, 2, 3
  sent_at        TEXT,
  opened_at      TEXT,
  clicked_at     TEXT,
  status         TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','sent','opened','clicked','suppressed'))
);

CREATE INDEX idx_rs_subscriber ON reactivation_sequences(subscriber_id, step);
```

---

## 2. Engagement Scoring — Determine Dormancy

```typescript
// src/dormancy.ts
import type { Env } from './types';

const DORMANT_DAYS = 90;
const REACTIVATION_COOLDOWN_DAYS = 30;

export interface DormantSubscriber {
  id: string;
  email: string;
}

export async function findDormantSubscribers(
  env: Env,
  limit = 500
): Promise<DormantSubscriber[]> {
  // Active subscribers with no opens/clicks in DORMANT_DAYS,
  // not already in a reactivation sequence started recently
  const { results } = await env.DB.prepare(
    `SELECT s.id, s.email
     FROM subscribers s
     WHERE s.status = 'active'
       AND (
         s.last_opened_at IS NULL
         OR s.last_opened_at < datetime('now', '-${DORMANT_DAYS} days')
       )
       AND (
         s.last_clicked_at IS NULL
         OR s.last_clicked_at < datetime('now', '-${DORMANT_DAYS} days')
       )
       AND s.id NOT IN (
         SELECT subscriber_id FROM reactivation_sequences
         WHERE sent_at > datetime('now', '-${REACTIVATION_COOLDOWN_DAYS} days')
       )
     LIMIT ?`
  ).bind(limit).all<DormantSubscriber>();

  return results;
}
```

---

## 3. Cron — Enrol Dormant Subscribers

```typescript
// src/enrol-cron.ts
import { findDormantSubscribers } from './dormancy';
import type { Env } from './types';

export interface ReactivationQueueMessage {
  subscriberId: string;
  email: string;
  step: number;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const dormant = await findDormantSubscribers(env);

    const stmts = dormant.map((s) =>
      env.DB.prepare(
        `INSERT OR IGNORE INTO reactivation_sequences
           (subscriber_id, step, status)
         VALUES (?, 1, 'pending')`
      ).bind(s.id)
    );

    if (stmts.length > 0) await env.DB.batch(stmts);

    // Mark subscribers as in-reactivation
    const ids = dormant.map((s) => `'${s.id.replace(/'/g, "''")}'`).join(',');
    if (ids) {
      await env.DB.prepare(
        `UPDATE subscribers SET status = 'reactivation' WHERE id IN (${ids})`
      ).run();
    }

    // Enqueue step 1 messages
    for (const s of dormant) {
      await env.REACTIVATION_QUEUE.send(
        { subscriberId: s.id, email: s.email, step: 1 } satisfies ReactivationQueueMessage,
        { contentType: 'json' }
      );
    }

    console.log(`Enrolled ${dormant.length} dormant subscribers`);
  },
};
```

---

## 4. Queue Consumer — Send Reactivation Email

```typescript
// src/consumer.ts
import type { Env } from './types';
import type { ReactivationQueueMessage } from './enrol-cron';

const STEP_SUBJECTS: Record<number, string> = {
  1: 'We miss you — here is what you have missed',
  2: 'Last chance to stay subscribed',
  3: 'You have been unsubscribed — click to resubscribe',
};

const STEP_DELAY_DAYS: Record<number, number> = { 1: 0, 2: 7, 3: 14 };

export default {
  async queue(
    batch: MessageBatch<ReactivationQueueMessage>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processStep(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('Reactivation step failed', err);
        msg.retry({ delaySeconds: 60 });
      }
    }
  },
};

async function processStep(
  { subscriberId, email, step }: ReactivationQueueMessage,
  env: Env
): Promise<void> {
  // Verify the sequence row exists and is still pending
  const row = await env.DB.prepare(
    `SELECT id, status FROM reactivation_sequences
     WHERE subscriber_id = ? AND step = ? AND status = 'pending'`
  ).bind(subscriberId, step).first<{ id: number; status: string }>();

  if (!row) return; // already processed or subscriber re-engaged

  const subject = STEP_SUBJECTS[step] ?? 'Checking in';
  const html = buildEmailHtml(step, subscriberId, env);

  const resp = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ from: env.FROM_ADDRESS, to: email, subject, html }),
  });

  if (!resp.ok) throw new Error(`Resend ${resp.status}`);

  await env.DB.prepare(
    `UPDATE reactivation_sequences SET status = 'sent', sent_at = datetime('now')
     WHERE subscriber_id = ? AND step = ?`
  ).bind(subscriberId, step).run();

  // Schedule next step if not final
  if (step < 3) {
    const nextStep = step + 1;
    const delaySeconds = STEP_DELAY_DAYS[nextStep] * 86_400;
    await env.REACTIVATION_QUEUE.send(
      { subscriberId, email, step: nextStep } satisfies ReactivationQueueMessage,
      { contentType: 'json', delaySeconds }
    );
    // Pre-insert the next sequence row
    await env.DB.prepare(
      `INSERT OR IGNORE INTO reactivation_sequences (subscriber_id, step, status)
       VALUES (?, ?, 'pending')`
    ).bind(subscriberId, nextStep).run();
  }
}

function buildEmailHtml(step: number, subscriberId: string, env: Env): string {
  const resubUrl =
    `https://prefs.${env.DOMAIN}/resubscribe?sid=${encodeURIComponent(subscriberId)}`;
  if (step === 3) {
    return `<p>You have been removed from our mailing list.
      <a >Click here to resubscribe</a>.</p>`;
  }
  return `<p>We noticed you have not opened our emails in a while.
    <a >Keep me subscribed</a></p>`;
}
```

---

## 5. Engagement Webhook — Cancel Reactivation on Re-engagement

```typescript
// Called by your open/click tracking endpoint
export async function recordEngagement(
  subscriberId: string,
  type: 'open' | 'click',
  env: Env
): Promise<void> {
  const field = type === 'open' ? 'last_opened_at' : 'last_clicked_at';

  await env.DB.prepare(
    `UPDATE subscribers
     SET ${field} = datetime('now'), status = 'active'
     WHERE id = ?`
  ).bind(subscriberId).run();

  // Cancel pending reactivation steps
  await env.DB.prepare(
    `UPDATE reactivation_sequences
     SET status = 'clicked'
     WHERE subscriber_id = ? AND status IN ('pending','sent')`
  ).bind(subscriberId).run();
}
```

---

## 6. Sunset — Suppress After Step 3

```typescript
// Run after step 3 send_at + 7 days (via another cron or Queue delay)
export async function sunsetUnresponsive(env: Env): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT subscriber_id FROM reactivation_sequences
     WHERE step = 3 AND status = 'sent'
       AND sent_at < datetime('now', '-7 days')`
  ).all<{ subscriber_id: string }>();

  if (results.length === 0) return;

  const ids = results.map((r) => `'${r.subscriber_id.replace(/'/g, "''")}'`).join(',');

  await env.DB.prepare(
    `UPDATE subscribers SET status = 'suppressed' WHERE id IN (${ids})`
  ).run();

  await env.DB.prepare(
    `UPDATE reactivation_sequences SET status = 'suppressed'
     WHERE subscriber_id IN (${ids}) AND step = 3 AND status = 'sent'`
  ).run();

  console.log(`Suppressed ${results.length} unresponsive subscribers`);
}
```

---

## Anti-patterns

- **Sending all three reactivation steps in a single blast**: Overloads dormant addresses and triggers spam complaints; space steps at least 7 days apart.
- **Not checking sequence status before sending**: Retry-without-check causes duplicate step emails.
- **Using random delays instead of `delaySeconds` in Queue.send**: Cloudflare Queues natively support message delay up to 12 hours (43200 s); for multi-day delays chain cron jobs.
- **Suppressing on non-open alone**: Apple MPP inflates open rates; rely on clicks and direct engagement signals for suppression decisions.

## Gotchas

- Cloudflare Queues `delaySeconds` maximum is 43200 (12 hours); for 7- and 14-day delays, schedule via a cron that queries D1 for sequence rows where `sent_at` is sufficiently old.
- String interpolation of IDs into SQL uses quoting; prefer parameterised queries with `IN` via a multi-bind loop when the SDK supports it, to avoid SQL injection risk.
- `INSERT OR IGNORE` does not throw on conflict; always verify with `meta.changes` if you need to detect whether the row was freshly inserted.
- Reactivation emails count toward complaint rate; if step-3 complaint rates exceed 0.08% stop the sequence and audit your original opt-in quality.

## Verification

```bash
# Check dormant subscriber count
wrangler d1 execute email-db --command \
  "SELECT COUNT(*) FROM subscribers WHERE status='active'
   AND last_opened_at < datetime('now','-90 days')"

# Track sequence progress
wrangler d1 execute email-db --command \
  "SELECT step, status, COUNT(*) FROM reactivation_sequences GROUP BY step, status"

# Confirm suppressed count after sunset run
wrangler d1 execute email-db --command \
  "SELECT COUNT(*) FROM subscribers WHERE status='suppressed'"
```

## Related

- `re-engagement-campaign.md`
- `email-sunset-policy.md`
- `email-engagement-score-decay-cron-workers.md`
- `email-drip-campaign-sequence-queues-workers.md`
- `email-list-hygiene-validation-workers.md`
- `email-complaint-rate-monitoring-workers-analytics.md`

## Sources

- https://developers.cloudflare.com/queues/configuration/batches-and-retries/#message-delay
- https://developers.cloudflare.com/d1/
- https://postmaster.google.com/u/0/managedomains (complaint rate thresholds)
- https://www.litmus.com/blog/email-reactivation-win-back-campaigns/
