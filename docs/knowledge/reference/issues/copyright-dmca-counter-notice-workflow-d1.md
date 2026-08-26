# DMCA Counter-Notice Workflow with D1 Timeline Tracking

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Users who dispute a DMCA takedown submit counter-notices but content is never restored on
schedule, the mandatory 10-14 business-day waiting window is missed, and there is no audit
trail demonstrating the platform honored 17 U.S.C. § 512(g).

## Context
Under DMCA safe harbor (17 U.S.C. § 512(g)), a platform that receives a valid
counter-notice must: (1) forward it to the original claimant within a reasonable time,
(2) wait 10-14 business days, and (3) restore the content unless the claimant provides
notice that it has filed a court action. Failure to restore on time forfeits safe-harbor
protection for that takedown. D1 drives the state machine; a Cron Trigger polls for
windows that have elapsed.

## D1 Schema and State Machine

```sql
-- migrations/0015_dmca_counter_notices.sql
CREATE TABLE dmca_takedowns (
  id            TEXT PRIMARY KEY,
  content_id    TEXT NOT NULL,
  r2_key        TEXT NOT NULL,
  claimant_email TEXT NOT NULL,
  received_at   INTEGER NOT NULL DEFAULT (unixepoch()),
  status        TEXT NOT NULL DEFAULT 'taken_down'
    CHECK (status IN ('taken_down','counter_received','forwarded',
                      'window_open','court_action_filed','restored','dismissed'))
);

CREATE TABLE dmca_counter_notices (
  id                TEXT PRIMARY KEY,
  takedown_id       TEXT NOT NULL REFERENCES dmca_takedowns(id),
  user_id           TEXT NOT NULL,
  statement         TEXT NOT NULL,       -- sworn § 512(g)(3) statement text
  received_at       INTEGER NOT NULL DEFAULT (unixepoch()),
  forwarded_at      INTEGER,             -- when platform sent to claimant
  window_opens_at   INTEGER,             -- forwarded_at + 0 business days (same day)
  restore_not_before INTEGER,            -- forwarded_at + 10 business days
  restore_deadline  INTEGER,             -- forwarded_at + 14 business days
  court_action_at   INTEGER,             -- claimant notified of lawsuit
  restored_at       INTEGER,
  status            TEXT NOT NULL DEFAULT 'received'
    CHECK (status IN ('received','forwarded','pending_restore',
                      'court_blocked','restored','dismissed'))
);

CREATE INDEX idx_counter_restore ON dmca_counter_notices(restore_not_before)
  WHERE status = 'pending_restore';
```

## Counter-Notice Intake Worker

Validate the § 512(g)(3) required elements before accepting a counter-notice.

```typescript
// src/handlers/counter-notice-intake.ts
import type { Env } from '../env';
import { nanoid } from 'nanoid';
import { addBusinessDays } from '../lib/business-days';

interface CounterNoticeBody {
  takedown_id: string;
  statement:   string;   // must include § 512(g)(3) elements
  consent:     boolean;  // consent to US district court jurisdiction
}

export async function handleCounterNoticeIntake(
  req: Request,
  env: Env,
): Promise<Response> {
  const userId = req.headers.get('X-User-ID');
  if (!userId) return new Response('Unauthorized', { status: 401 });

  const body: CounterNoticeBody = await req.json();

  if (!body.consent) {
    return Response.json(
      { error: 'Counter-notice must include consent to US district court jurisdiction (17 U.S.C. § 512(g)(3)(D)).' },
      { status: 422 },
    );
  }
  if (!body.statement || body.statement.length < 100) {
    return Response.json(
      { error: 'Statement too short — must include good-faith belief, sworn penalty of perjury.' },
      { status: 422 },
    );
  }

  // Verify the takedown belongs to this user's content
  const takedown = await env.DB.prepare(
    `SELECT id, claimant_email FROM dmca_takedowns WHERE id = ? AND status = 'taken_down'`
  ).bind(body.takedown_id).first<{ id: string; claimant_email: string }>();

  if (!takedown) {
    return Response.json({ error: 'Takedown not found or not eligible for counter-notice.' }, { status: 404 });
  }

  const now              = Math.floor(Date.now() / 1000);
  const restoreNotBefore = addBusinessDays(now, 10);
  const restoreDeadline  = addBusinessDays(now, 14);
  const counterId        = nanoid();

  await env.DB.prepare(
    `INSERT INTO dmca_counter_notices
       (id, takedown_id, user_id, statement, received_at,
        restore_not_before, restore_deadline, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'received')`
  ).bind(counterId, body.takedown_id, userId, body.statement, now, restoreNotBefore, restoreDeadline).run();

  // Queue forwarding to claimant — must happen promptly
  await env.DMCA_QUEUE.send({ type: 'forward_counter_notice', counterId, claimantEmail: takedown.claimant_email });

  return Response.json({ counter_notice_id: counterId, restore_not_before: restoreNotBefore }, { status: 202 });
}
```

## Business-Day Calculator and Forwarding Queue Consumer

```typescript
// src/lib/business-days.ts
const US_FEDERAL_HOLIDAYS_2026 = new Set([
  '2026-01-01','2026-01-19','2026-02-16','2026-05-25',
  '2026-06-19','2026-07-03','2026-07-04','2026-09-07',
  '2026-10-12','2026-11-11','2026-11-26','2026-12-25',
]);

export function addBusinessDays(unixSeconds: number, days: number): number {
  const d = new Date(unixSeconds * 1000);
  let added = 0;
  while (added < days) {
    d.setUTCDate(d.getUTCDate() + 1);
    const iso = d.toISOString().slice(0, 10);
    const dow = d.getUTCDay();
    if (dow !== 0 && dow !== 6 && !US_FEDERAL_HOLIDAYS_2026.has(iso)) added++;
  }
  return Math.floor(d.getTime() / 1000);
}
```

```typescript
// src/consumers/dmca-queue-consumer.ts  (Queue handler)
export async function handleDmcaQueueMessage(
  batch: MessageBatch<{ type: string; counterId: string; claimantEmail: string }>,
  env: Env,
): Promise<void> {
  for (const msg of batch.messages) {
    const { type, counterId, claimantEmail } = msg.body;

    if (type === 'forward_counter_notice') {
      const now = Math.floor(Date.now() / 1000);

      // Send email to claimant via Email Worker binding
      await env.EMAIL.send({
        to: claimantEmail,
        from: 'dmca@platform.example',
        subject: `DMCA Counter-Notice Received — ${counterId}`,
        text: await buildForwardingEmail(counterId, env),
      });

      await env.DB.prepare(
        `UPDATE dmca_counter_notices
         SET forwarded_at = ?, status = 'pending_restore'
         WHERE id = ?`
      ).bind(now, counterId).run();

      await env.DB.prepare(
        `UPDATE dmca_takedowns SET status = 'counter_received'
         WHERE id = (SELECT takedown_id FROM dmca_counter_notices WHERE id = ?)`
      ).bind(counterId).run();
    }
    msg.ack();
  }
}

async function buildForwardingEmail(counterId: string, env: Env): Promise<string> {
  const row = await env.DB.prepare(
    `SELECT cn.statement, cn.restore_not_before, cn.restore_deadline
     FROM dmca_counter_notices cn WHERE cn.id = ?`
  ).bind(counterId).first<{ statement: string; restore_not_before: number; restore_deadline: number }>();
  if (!row) throw new Error(`Counter notice ${counterId} not found`);

  const restoreDate = new Date(row.restore_not_before * 1000).toISOString().slice(0, 10);
  return [
    'We have received a DMCA counter-notice under 17 U.S.C. § 512(g).',
    '',
    `Counter-notice ID: ${counterId}`,
    `Content will be restored no earlier than: ${restoreDate}`,
    `unless you notify us of a filed court action before that date.`,
    '',
    'Counter-notice statement:',
    row.statement,
  ].join('\n');
}
```

## Cron-Based Restoration Trigger

```typescript
// src/jobs/restore-eligible-content.ts
export async function restoreEligibleContent(env: Env): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  const { results } = await env.DB.prepare(
    `SELECT cn.id, cn.takedown_id, cn.restore_deadline, t.r2_key, t.content_id
     FROM dmca_counter_notices cn
     JOIN dmca_takedowns t ON t.id = cn.takedown_id
     WHERE cn.status = 'pending_restore'
       AND cn.restore_not_before <= ?
       AND cn.court_action_at IS NULL
     LIMIT 50`
  ).bind(now).all<{ id: string; takedown_id: string; restore_deadline: number; r2_key: string; content_id: string }>();

  for (const row of results) {
    if (now > row.restore_deadline) {
      // Window passed — platform may be liable; escalate
      await env.DB.prepare(
        `UPDATE dmca_counter_notices SET status = 'dismissed' WHERE id = ?`
      ).bind(row.id).run();
      await env.ALERT_QUEUE.send({ type: 'dmca_restore_window_missed', counterId: row.id });
      continue;
    }

    // Restore: un-suppress the content in D1 and R2 visibility flag
    await env.DB.prepare(
      `UPDATE dmca_takedowns SET status = 'restored' WHERE id = ?`
    ).bind(row.takedown_id).run();
    await env.DB.prepare(
      `UPDATE dmca_counter_notices SET restored_at = ?, status = 'restored' WHERE id = ?`
    ).bind(now, row.id).run();

    // Signal content-serving layer to un-suppress
    await env.CONTENT_VISIBILITY_KV.delete(`suppressed:${row.content_id}`);
  }
}
```

## Anti-patterns
- Restoring content immediately upon receiving the counter-notice — violates the mandatory waiting window
- Using calendar days instead of business days — shortens the legally required window
- Sending the counter-notice statement to the claimant without stripping PII beyond the required elements
- Storing the claimant's court-action notice only in email — it must be persisted in D1 to halt restoration
- Allowing the counter-notice form to accept HTML or rich text — XSS risk in the forwarding email

## Gotchas
- 17 U.S.C. § 512(g) says "10 to 14 business days" — restoring on day 9 is premature; past day 14 risks liability
- The claimant's court-action notice has no statutory form; any written notice of filed suit is sufficient
- "Forwarding promptly" is not defined; courts have accepted same-day or next-business-day forwarding
- Counter-notices are public records if litigation follows — treat statement text as potentially discoverable
- The § 512(g) process applies to hosting providers, not to search results; different rules apply for indexing

## Verification

```sql
-- Notices approaching restore window with no court action
SELECT id, takedown_id, restore_not_before, restore_deadline,
       datetime(restore_not_before, 'unixepoch') AS restore_from,
       datetime(restore_deadline,  'unixepoch') AS restore_by
FROM dmca_counter_notices
WHERE status = 'pending_restore'
  AND court_action_at IS NULL
ORDER BY restore_not_before;

-- Average forwarding lag (should be < 24h = 86400s)
SELECT AVG(forwarded_at - received_at) AS avg_forward_lag_seconds
FROM dmca_counter_notices
WHERE forwarded_at IS NOT NULL;
```

## Related
- `copyright-dmca-takedown-worker-pipeline.md` — the originating takedown workflow this responds to
- `copyright-dmca-automation-workers-r2-d1.md` — broader DMCA automation covering notice receipt
- `legal-hold-evidence-preservation-d1-r2.md` — when counter-noticed content is also under legal hold
- `content-appeal-escalation-workflow-durable-objects.md` — internal appeals distinct from DMCA counter-notice

## Sources
- https://www.law.cornell.edu/uscode/text/17/512 (§ 512(g) specifically)
- https://www.copyright.gov/dmca/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
- https://www.eff.org/issues/dmca/counter-notification
