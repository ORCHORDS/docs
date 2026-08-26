# Email Sequence Drip Pause/Resume with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A user unsubscribes mid-sequence, a sales rep puts a prospect "on hold", or a payment fails — the drip sequence must freeze at its current step, persist that state durably, and resume from exactly that step days or weeks later without re-sending already-delivered emails. Cloudflare Queues alone cannot model this; the pause/resume contract lives in D1.

---

## Context

Cloudflare Workers + Queues handle high-volume drip fan-out well, but Queues offer no native "pause" primitive. The solution is a D1-backed state machine: each enrollment row tracks `(contact_id, sequence_id, current_step, status, resume_at)`. Workers enqueue the next step only when `status = 'active'`; a pause writes `status = 'paused'` and clears the in-flight queue message by treating the step as a no-op on delivery.

Supported statuses: `active | paused | cancelled | completed | error`.

---

## D1 Schema

```sql
CREATE TABLE sequence_enrollments (
  id              TEXT PRIMARY KEY,           -- ulid
  contact_id      TEXT NOT NULL,
  sequence_id     TEXT NOT NULL,
  current_step    INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'active'
                  CHECK(status IN ('active','paused','cancelled','completed','error')),
  paused_at       INTEGER,                    -- epoch ms
  resume_at       INTEGER,                    -- epoch ms, null = indefinite pause
  error_message   TEXT,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);

CREATE INDEX idx_enroll_contact   ON sequence_enrollments(contact_id);
CREATE INDEX idx_enroll_resume    ON sequence_enrollments(status, resume_at)
  WHERE status = 'paused';

CREATE TABLE sequence_steps (
  sequence_id     TEXT NOT NULL,
  step_index      INTEGER NOT NULL,
  delay_hours     INTEGER NOT NULL DEFAULT 0,
  template_id     TEXT NOT NULL,
  subject         TEXT NOT NULL,
  PRIMARY KEY (sequence_id, step_index)
);

CREATE TABLE sequence_send_log (
  enrollment_id   TEXT NOT NULL,
  step_index      INTEGER NOT NULL,
  sent_at         INTEGER NOT NULL,
  message_id      TEXT,
  PRIMARY KEY (enrollment_id, step_index)
);
```

---

## Enrollment and First Step Dispatch

```typescript
// src/enroll.ts
import { Env } from './types';
import { ulid } from 'ulid';

export async function enrollContact(
  env: Env,
  contactId: string,
  sequenceId: string
): Promise<string> {
  const id = ulid();
  const now = Date.now();

  await env.DB.prepare(`
    INSERT INTO sequence_enrollments
      (id, contact_id, sequence_id, current_step, status, created_at, updated_at)
    VALUES (?, ?, ?, 0, 'active', ?, ?)
    ON CONFLICT (id) DO NOTHING
  `).bind(id, contactId, sequenceId, now, now).run();

  // Dispatch step 0 immediately
  await env.DRIP_QUEUE.send({
    type: 'drip_step',
    enrollmentId: id,
    stepIndex: 0,
  });

  return id;
}
```

---

## Queue Consumer: Step Execution with State Guard

```typescript
// src/queue-consumer.ts
import { Env, DripMessage } from './types';

export default {
  async queue(batch: MessageBatch<DripMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { enrollmentId, stepIndex } = msg.body;

      // Fetch enrollment — single row, cheap
      const enrollment = await env.DB.prepare(`
        SELECT status, current_step, sequence_id, contact_id
        FROM sequence_enrollments
        WHERE id = ?
      `).bind(enrollmentId).first<{
        status: string;
        current_step: number;
        sequence_id: string;
        contact_id: string;
      }>();

      if (!enrollment) { msg.ack(); continue; }

      // Stale message guard: enrollment already advanced past this step
      if (enrollment.status !== 'active' || enrollment.current_step !== stepIndex) {
        msg.ack(); // silently discard; pause/cancel wrote new status
        continue;
      }

      // Fetch step definition
      const step = await env.DB.prepare(`
        SELECT template_id, subject, delay_hours
        FROM sequence_steps
        WHERE sequence_id = ? AND step_index = ?
      `).bind(enrollment.sequence_id, stepIndex).first<{
        template_id: string;
        subject: string;
        delay_hours: number;
      }>();

      if (!step) {
        await markCompleted(env, enrollmentId);
        msg.ack();
        continue;
      }

      try {
        const messageId = await sendEmail(env, enrollment.contact_id, step);
        await advanceEnrollment(env, enrollmentId, stepIndex, step, messageId);
        msg.ack();
      } catch (err) {
        await markError(env, enrollmentId, String(err));
        msg.retry({ delaySeconds: 300 });
      }
    }
  },
};

async function advanceEnrollment(
  env: Env,
  enrollmentId: string,
  stepIndex: number,
  step: { delay_hours: number; template_id: string },
  messageId: string
): Promise<void> {
  const now = Date.now();
  const nextStep = stepIndex + 1;

  // Check if next step exists
  const hasNext = await env.DB.prepare(`
    SELECT 1 FROM sequence_steps
    WHERE sequence_id = (
      SELECT sequence_id FROM sequence_enrollments WHERE id = ?
    ) AND step_index = ?
  `).bind(enrollmentId, nextStep).first();

  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO sequence_send_log (enrollment_id, step_index, sent_at, message_id)
      VALUES (?, ?, ?, ?)
    `).bind(enrollmentId, stepIndex, now, messageId),

    hasNext
      ? env.DB.prepare(`
          UPDATE sequence_enrollments
          SET current_step = ?, updated_at = ?
          WHERE id = ?
        `).bind(nextStep, now, enrollmentId)
      : env.DB.prepare(`
          UPDATE sequence_enrollments
          SET status = 'completed', updated_at = ?
          WHERE id = ?
        `).bind(now, enrollmentId),
  ]);

  if (hasNext) {
    // Enqueue next step after delay
    await env.DRIP_QUEUE.send(
      { type: 'drip_step', enrollmentId, stepIndex: nextStep },
      { delaySeconds: step.delay_hours * 3600 }
    );
  }
}
```

---

## Pause and Resume API

```typescript
// src/pause-resume.ts
import { Env } from './types';

export async function pauseEnrollment(
  env: Env,
  enrollmentId: string,
  resumeAt?: number    // epoch ms; undefined = indefinite
): Promise<void> {
  const now = Date.now();

  const result = await env.DB.prepare(`
    UPDATE sequence_enrollments
    SET status = 'paused', paused_at = ?, resume_at = ?, updated_at = ?
    WHERE id = ? AND status = 'active'
  `).bind(now, resumeAt ?? null, now, enrollmentId).run();

  if (result.meta.changes === 0) {
    throw new Error('Enrollment not found or not in active state');
  }
  // In-flight queue messages are naturally discarded by the stale-step guard above
}

export async function resumeEnrollment(
  env: Env,
  enrollmentId: string
): Promise<void> {
  const now = Date.now();

  const enrollment = await env.DB.prepare(`
    SELECT current_step, status FROM sequence_enrollments WHERE id = ?
  `).bind(enrollmentId).first<{ current_step: number; status: string }>();

  if (!enrollment || enrollment.status !== 'paused') {
    throw new Error('Enrollment not paused');
  }

  await env.DB.prepare(`
    UPDATE sequence_enrollments
    SET status = 'active', paused_at = NULL, resume_at = NULL, updated_at = ?
    WHERE id = ?
  `).bind(now, enrollmentId).run();

  // Re-dispatch the pending step immediately
  await env.DRIP_QUEUE.send({
    type: 'drip_step',
    enrollmentId,
    stepIndex: enrollment.current_step,
  });
}
```

---

## Cron: Auto-Resume Timed Pauses

```typescript
// src/cron.ts — runs every 5 minutes via [triggers] crons in wrangler.toml
export async function handleAutoResume(env: Env): Promise<void> {
  const now = Date.now();

  const due = await env.DB.prepare(`
    SELECT id, current_step
    FROM sequence_enrollments
    WHERE status = 'paused' AND resume_at IS NOT NULL AND resume_at <= ?
    LIMIT 100
  `).bind(now).all<{ id: string; current_step: number }>();

  for (const row of due.results) {
    await resumeEnrollment(env, row.id); // re-uses the function above
  }
}
```

---

## Anti-patterns

- **Relying on queue TTL for pause** — messages will be dropped permanently when the TTL expires; the enrollment becomes stranded with no recovery path.
- **Updating `current_step` before the send succeeds** — if the HTTP call to the ESP fails after advancing the counter, that step is silently skipped.
- **Using KV for enrollment state** — KV's eventual consistency can cause a resumed enrollment to read a stale `status = 'active'` and double-send a step.
- **Not guarding on `current_step` in the consumer** — without the stale-message guard, a re-enqueued message after resume fires the same step twice.

---

## Gotchas

- Cloudflare Queues `delaySeconds` max is 12 hours (43 200 s) as of 2025; for longer drip intervals, enqueue a "wake-up" event and schedule from there, or use a cron loop.
- D1 `batch()` is not a true transaction in the serializable sense across multiple writes in high-concurrency scenarios; use a single `UPDATE … WHERE status = 'active'` as an optimistic lock.
- The `sequence_send_log` is critical for idempotency: check it before sending when retrying consumer errors.

---

## Verification

```bash
# Enroll a test contact
curl -X POST https://workers.example.com/enroll \
  -H "Content-Type: application/json" \
  -d '{"contactId":"c_001","sequenceId":"onboarding"}'

# Pause immediately
curl -X POST https://workers.example.com/enrollments/ENROLL_ID/pause \
  -d '{"resumeAt": 1761264000000}'

# Confirm status in D1
wrangler d1 execute DB --command \
  "SELECT status, current_step, resume_at FROM sequence_enrollments WHERE id='ENROLL_ID'"

# Resume manually
curl -X POST https://workers.example.com/enrollments/ENROLL_ID/resume

# Confirm send log
wrangler d1 execute DB --command \
  "SELECT * FROM sequence_send_log WHERE enrollment_id='ENROLL_ID' ORDER BY step_index"
```

---

## Related

- `email-drip-campaign-sequence-queues-workers.md`
- `email-digest-batching-queues-d1-workers.md`
- `email-rate-limit-per-recipient-d1-sliding-window.md`
- `email-consent-audit-trail-d1.md`
- `transactional-queue-cloudflare-queues.md`

---

## Sources

- Cloudflare Queues delayed delivery: https://developers.cloudflare.com/queues/configuration/javascript-apis/#messagesendoptions
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
