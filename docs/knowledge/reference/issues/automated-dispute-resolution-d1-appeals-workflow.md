# Automated Moderation Dispute Resolution: D1 Appeals State Machine

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Moderation Appeals Problem

When content is removed, accounts are suspended, or visibility is reduced, users have a legal and policy right to appeal in most jurisdictions (EU DSA Article 20, UK OSA, etc.). Without a structured appeals workflow, appeals arrive as support tickets, SLAs are tracked in spreadsheets, escalations are manual, and stale appeals quietly breach legal deadlines. At scale, hundreds of appeals per day overwhelm a small trust-and-safety team.

An automated state machine backed by D1 provides: deterministic status transitions, enforced SLA windows, automatic escalation when deadlines lapse, and a traceable audit record for legal compliance. Workers cron jobs handle stale-appeal detection and escalation. The human review queue integrates via a Worker-served admin API that updates state atomically.

The state machine has five states: `submitted` → `under_review` → `escalated` | `resolved_upheld` | `resolved_reversed`. Transitions are guarded — only valid transitions execute; invalid ones are rejected with a 409. Every transition writes to an immutable `appeal_events` log table so compliance teams can reconstruct the full history.

## Context

- Runtime: Cloudflare Workers + D1
- Cron: Cloudflare Workers cron triggers (scheduled handlers)
- Queue: Cloudflare Queues for human review integration
- SLA targets: initial response 72 h, final decision 30 days (EU DSA Article 17)

## D1 Schema and State Machine Definition

```ts
// schema.sql (run via D1 migration)
// CREATE TABLE appeals (
//   id              TEXT PRIMARY KEY,
//   content_id      TEXT NOT NULL,
//   user_id         TEXT NOT NULL,
//   moderation_id   TEXT NOT NULL,
//   state           TEXT NOT NULL DEFAULT 'submitted',
//   created_at      INTEGER NOT NULL,
//   updated_at      INTEGER NOT NULL,
//   sla_deadline    INTEGER NOT NULL,   -- epoch ms, 72 h from created_at
//   final_deadline  INTEGER NOT NULL,   -- epoch ms, 30 days from created_at
//   reviewer_id     TEXT,
//   resolution_note TEXT
// );
// CREATE INDEX idx_appeals_state ON appeals (state);
// CREATE INDEX idx_appeals_deadline ON appeals (sla_deadline);
//
// CREATE TABLE appeal_events (
//   id         INTEGER PRIMARY KEY AUTOINCREMENT,
//   appeal_id  TEXT NOT NULL,
//   from_state TEXT NOT NULL,
//   to_state   TEXT NOT NULL,
//   actor      TEXT NOT NULL,
//   note       TEXT,
//   ts         INTEGER NOT NULL
// );

type AppealState = 'submitted' | 'under_review' | 'escalated' | 'resolved_upheld' | 'resolved_reversed';

const VALID_TRANSITIONS: Record<AppealState, AppealState[]> = {
  submitted:           ['under_review'],
  under_review:        ['escalated', 'resolved_upheld', 'resolved_reversed'],
  escalated:           ['resolved_upheld', 'resolved_reversed'],
  resolved_upheld:     [],
  resolved_reversed:   [],
};

export function isValidTransition(from: AppealState, to: AppealState): boolean {
  return (VALID_TRANSITIONS[from] ?? []).includes(to);
}
```

## Appeal Submission and State Transition Worker

```ts
// workers/appeals.ts
import { isValidTransition, AppealState } from '../lib/state-machine';

const SLA_72H_MS  = 72 * 60 * 60 * 1000;
const SLA_30D_MS  = 30 * 24 * 60 * 60 * 1000;

export async function submitAppeal(request: Request, env: Env): Promise<Response> {
  const { contentId, userId, moderationId, reason } = await request.json<{
    contentId: string; userId: string; moderationId: string; reason: string;
  }>();

  const appealId = crypto.randomUUID();
  const now = Date.now();

  await env.DB.prepare(
    `INSERT INTO appeals (id, content_id, user_id, moderation_id, state, created_at, updated_at, sla_deadline, final_deadline)
     VALUES (?, ?, ?, ?, 'submitted', ?, ?, ?, ?)`
  ).bind(appealId, contentId, userId, moderationId, now, now, now + SLA_72H_MS, now + SLA_30D_MS).run();

  await env.DB.prepare(
    `INSERT INTO appeal_events (appeal_id, from_state, to_state, actor, note, ts)
     VALUES (?, '', 'submitted', ?, ?, ?)`
  ).bind(appealId, userId, reason, now).run();

  // Notify human review queue
  await env.REVIEW_QUEUE.send({ appealId, contentId, userId, reason, submittedAt: now });

  return Response.json({ appealId, state: 'submitted', slaDeadline: new Date(now + SLA_72H_MS).toISOString() }, { status: 201 });
}

export async function transitionAppeal(
  appealId: string,
  toState: AppealState,
  actor: string,
  note: string,
  env: Env
): Promise<Response> {
  const row = await env.DB.prepare(`SELECT state FROM appeals WHERE id = ?`).bind(appealId).first<{ state: AppealState }>();
  if (!row) return Response.json({ error: 'Appeal not found' }, { status: 404 });

  if (!isValidTransition(row.state, toState)) {
    return Response.json({ error: `Invalid transition: ${row.state} → ${toState}`, code: 'INVALID_TRANSITION' }, { status: 409 });
  }

  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare(`UPDATE appeals SET state = ?, updated_at = ?, reviewer_id = ? WHERE id = ?`)
      .bind(toState, now, actor, appealId),
    env.DB.prepare(`INSERT INTO appeal_events (appeal_id, from_state, to_state, actor, note, ts) VALUES (?, ?, ?, ?, ?, ?)`)
      .bind(appealId, row.state, toState, actor, note, now),
  ]);

  return Response.json({ appealId, previousState: row.state, newState: toState });
}
```

## Workers Cron: Stale Appeal Detection and Auto-Escalation

```ts
// workers/appeals-cron.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const now = Date.now();

    // Escalate appeals that missed the 72 h SLA and are still in submitted/under_review
    const stale = await env.DB.prepare(
      `SELECT id, state FROM appeals
       WHERE state IN ('submitted', 'under_review')
         AND sla_deadline < ?
         AND state != 'escalated'`
    ).bind(now).all<{ id: string; state: AppealState }>();

    for (const appeal of stale.results) {
      await env.DB.batch([
        env.DB.prepare(`UPDATE appeals SET state = 'escalated', updated_at = ? WHERE id = ?`).bind(now, appeal.id),
        env.DB.prepare(`INSERT INTO appeal_events (appeal_id, from_state, to_state, actor, note, ts) VALUES (?, ?, 'escalated', 'system-cron', 'SLA breach auto-escalation', ?)`)
          .bind(appeal.id, appeal.state, now),
      ]);
      ctx.waitUntil(env.REVIEW_QUEUE.send({ appealId: appeal.id, priority: 'urgent', reason: 'sla_breach' }));
    }

    // Detect appeals approaching final 30-day deadline (flag 48 h before)
    const warning48h = now + 48 * 60 * 60 * 1000;
    const nearFinal = await env.DB.prepare(
      `SELECT id FROM appeals
       WHERE state IN ('submitted', 'under_review', 'escalated')
         AND final_deadline < ?`
    ).bind(warning48h).all<{ id: string }>();

    for (const appeal of nearFinal.results) {
      ctx.waitUntil(env.REVIEW_QUEUE.send({ appealId: appeal.id, priority: 'critical', reason: 'final_deadline_warning' }));
    }
  },
};
```

## Anti-patterns

- Storing state only in KV — KV lacks transactions; concurrent transitions corrupt state
- Allowing direct state updates without an event log — breaks compliance audit trails
- Using soft deletes instead of `resolved_*` terminal states — terminal states must be immutable
- Running SLA cron more frequently than once per minute — Cloudflare cron minimum is 1 minute
- Resolving appeals without notifying the user — DSA Article 17 requires notification

## Gotchas

- D1 `batch()` is not a true distributed transaction — if the second statement fails, the first has already committed; use a compensating update
- Cron triggers fire at most once per minute; `sla_deadline` precision below 60 s is meaningless
- `appeal_events` is append-only — never DELETE from it; add a `deleted_at` flag on `appeals` only
- Workers cron scheduled handler must complete within 30 s CPU time; paginate large stale-appeal batches
- EU DSA Article 20 requires appeals to be free of charge and accessible without undue burden

## Verification

```ts
// Verify that a double-transition from 'submitted' to 'submitted' is rejected
const res = await transitionAppeal('appeal-123', 'submitted', 'reviewer-1', 'test', mockEnv);
console.assert(res.status === 409, 'Self-transition must return 409');

// Verify that submitted → under_review succeeds
const res2 = await transitionAppeal('appeal-123', 'under_review', 'reviewer-1', 'picked up', mockEnv);
console.assert(res2.status === 200, 'Valid transition must return 200');
```

## Related

- `documentation/docs/policies/issues/cross-platform-content-policy-enforcement-workers.md`
- `documentation/docs/policies/issues/dsa-risk-assessment.md`
- `documentation/docs/policies/issues/d1-column-affinity-gotcha.md`
- `documentation/docs/policies/issues/blameless-postmortem.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065 (DSA Articles 17, 20)
- https://developers.cloudflare.com/queues/
