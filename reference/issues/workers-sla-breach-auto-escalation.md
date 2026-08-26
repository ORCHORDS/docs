# Auto-Escalating SLA Breaches Using Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Support tickets are missing SLA deadlines without triggering alerts. Teams only discover breaches after customers complain. You need a system that proactively warns responders at 75% of SLA time elapsed, escalates at 90%, and pages on-call at 100% — with snooze capability and full escalation history.

## Context

Cloudflare Workers Cron Triggers run on a configurable schedule and can query a D1 database for ticket state. Because Workers are stateless, all SLA state lives in D1. PagerDuty and Slack notifications are fired via `fetch`. Each escalation event is appended to an `escalation_log` table so auditors can reconstruct what happened and when.

SLA tiers supported:
- **P1** – 1 hour
- **P2** – 4 hours
- **P3** – 8 hours
- **P4** – 24 hours

## Solution

```typescript
// workers-sla-escalation/src/index.ts
import { Env } from './types';

export interface Env {
  DB: D1Database;
  PAGERDUTY_ROUTING_KEY: string;
  SLACK_WEBHOOK_URL: string;
  SNOOZE_SECRET: string;
}

const SLA_HOURS: Record<string, number> = {
  P1: 1,
  P2: 4,
  P3: 8,
  P4: 24,
};

type EscalationTier = 'warn' | 'escalate' | 'breach';

interface Ticket {
  id: string;
  priority: string;
  created_at: number; // unix ms
  snoozed_until: number | null;
  escalation_tier: EscalationTier | null;
  assignee_email: string;
  title: string;
}

function pctElapsed(ticket: Ticket, nowMs: number): number {
  const slaMs = (SLA_HOURS[ticket.priority] ?? 8) * 3_600_000;
  return (nowMs - ticket.created_at) / slaMs;
}

function tierForPct(pct: number): EscalationTier | null {
  if (pct >= 1.0) return 'breach';
  if (pct >= 0.9) return 'escalate';
  if (pct >= 0.75) return 'warn';
  return null;
}

async function notifySlack(env: Env, ticket: Ticket, tier: EscalationTier, pct: number) {
  const emoji = tier === 'breach' ? '🚨' : tier === 'escalate' ? '⚠️' : '🟡';
  const body = {
    text: `${emoji} *SLA ${tier.toUpperCase()}* — Ticket ${ticket.id} (${ticket.priority})\n` +
          `*${ticket.title}*\nAssignee: ${ticket.assignee_email}\n` +
          `SLA elapsed: ${(pct * 100).toFixed(0)}%`,
  };
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function triggerPagerDuty(env: Env, ticket: Ticket) {
  const payload = {
    routing_key: env.PAGERDUTY_ROUTING_KEY,
    event_action: 'trigger',
    dedup_key: `sla-breach-${ticket.id}`,
    payload: {
      summary: `SLA BREACH — ${ticket.priority} ticket ${ticket.id}: ${ticket.title}`,
      severity: 'critical',
      source: 'sla-escalation-worker',
      custom_details: {
        ticket_id: ticket.id,
        assignee: ticket.assignee_email,
        priority: ticket.priority,
      },
    },
  };
  await fetch('https://events.pagerduty.com/v2/enqueue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

async function logEscalation(
  env: Env,
  ticketId: string,
  tier: EscalationTier,
  pct: number,
  nowMs: number,
) {
  await env.DB.prepare(
    `INSERT INTO escalation_log (ticket_id, tier, pct_elapsed, fired_at)
     VALUES (?, ?, ?, ?)`,
  )
    .bind(ticketId, tier, pct, nowMs)
    .run();
}

async function scanBreaches(env: Env) {
  const nowMs = Date.now();

  const { results } = await env.DB.prepare(
    `SELECT id, priority, created_at, snoozed_until, escalation_tier, assignee_email, title
     FROM tickets
     WHERE resolved_at IS NULL
       AND (snoozed_until IS NULL OR snoozed_until < ?)`,
  )
    .bind(nowMs)
    .all<Ticket>();

  for (const ticket of results) {
    const pct = pctElapsed(ticket, nowMs);
    const newTier = tierForPct(pct);

    if (!newTier) continue;

    // Only escalate if moving to a higher tier than already recorded
    const tierOrder: Record<string, number> = { warn: 1, escalate: 2, breach: 3 };
    const currentOrder = ticket.escalation_tier ? (tierOrder[ticket.escalation_tier] ?? 0) : 0;
    const newOrder = tierOrder[newTier];
    if (newOrder <= currentOrder) continue;

    // Send notifications
    await notifySlack(env, ticket, newTier, pct);
    if (newTier === 'breach') {
      await triggerPagerDuty(env, ticket);
    }

    // Persist new tier and log
    await env.DB.prepare(
      `UPDATE tickets SET escalation_tier = ? WHERE id = ?`,
    )
      .bind(newTier, ticket.id)
      .run();

    await logEscalation(env, ticket.id, newTier, pct, nowMs);
  }
}

// Snooze API: POST /snooze  { ticket_id, minutes }
async function handleSnooze(req: Request, env: Env): Promise<Response> {
  const auth = req.headers.get('X-Snooze-Secret');
  if (auth !== env.SNOOZE_SECRET) {
    return new Response('Unauthorized', { status: 401 });
  }
  const { ticket_id, minutes } = await req.json<{ ticket_id: string; minutes: number }>();
  if (!ticket_id || !minutes || minutes < 1 || minutes > 1440) {
    return new Response('Invalid payload', { status: 400 });
  }
  const snoozedUntil = Date.now() + minutes * 60_000;
  await env.DB.prepare(`UPDATE tickets SET snoozed_until = ? WHERE id = ?`)
    .bind(snoozedUntil, ticket_id)
    .run();
  return Response.json({ ok: true, snoozed_until: new Date(snoozedUntil).toISOString() });
}

export default {
  // Cron: runs every 5 minutes
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    await scanBreaches(env);
  },

  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (req.method === 'POST' && url.pathname === '/snooze') {
      return handleSnooze(req, env);
    }
    return new Response('Not found', { status: 404 });
  },
};
```

**D1 schema:**

```sql
CREATE TABLE tickets (
  id              TEXT PRIMARY KEY,
  priority        TEXT NOT NULL,         -- P1 | P2 | P3 | P4
  title           TEXT NOT NULL,
  assignee_email  TEXT NOT NULL,
  created_at      INTEGER NOT NULL,      -- unix ms
  resolved_at     INTEGER,
  snoozed_until   INTEGER,
  escalation_tier TEXT                   -- warn | escalate | breach
);

CREATE TABLE escalation_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id   TEXT NOT NULL,
  tier        TEXT NOT NULL,
  pct_elapsed REAL NOT NULL,
  fired_at    INTEGER NOT NULL
);
```

**wrangler.toml snippet:**

```toml
[triggers]
crons = ["*/5 * * * *"]

[[d1_databases]]
binding = "DB"
database_name = "support-tickets"
database_id   = "<your-d1-id>"
```

## Implementation Details

- `pctElapsed` computes how far through the SLA window the ticket is, using `created_at` as the clock start.
- Tier progression is strictly monotonic: a ticket that has already received an `escalate` notification will not re-send `warn`.
- Snooze resets `snoozed_until`; the cron's `WHERE` clause silently skips snoozed tickets until the window expires.
- PagerDuty's `dedup_key` prevents duplicate incidents for the same ticket.
- `escalation_log` retains the full history of when each tier fired and the precise SLA percentage at that moment.

## Anti-patterns

- **Storing SLA deadlines as absolute timestamps only.** Always store `created_at` + `priority` separately so you can recompute percentages and support retroactive SLA changes.
- **Re-alerting on every cron run.** Without the tier monotonicity guard, responders receive dozens of duplicate notifications per breach.
- **Missing snooze upper bound.** Allowing indefinitely long snoozes defeats the purpose of SLA tracking; cap at a sensible maximum (e.g. 1440 minutes / 24 hours).
- **Firing PagerDuty without a dedup key.** PagerDuty will create multiple open incidents for the same underlying event.

## Gotchas

- Workers Cron accuracy is approximately ±30 seconds; do not use it for sub-minute SLA windows.
- D1 `INTEGER` columns store unix milliseconds as 64-bit integers; JavaScript's `Date.now()` is already in ms — no conversion needed.
- If a ticket is resolved between cron runs, `resolved_at IS NULL` in the query ensures it is excluded automatically.
- Ensure `SNOOZE_SECRET` is stored as a Worker Secret (`wrangler secret put SNOOZE_SECRET`), not in `wrangler.toml`.

## Verification

1. Insert a P1 ticket with `created_at = Date.now() - 55 * 60_000` (55 min ago). Trigger the cron manually via `wrangler dev` and assert a `warn` row appears in `escalation_log`.
2. Advance `created_at` to 54 min ago (90% elapsed). Re-trigger. Assert an `escalate` row is inserted and Slack receives the message.
3. Set `created_at` to 60+ min ago. Re-trigger. Assert a `breach` row is inserted and PagerDuty receives an event.
4. Call `POST /snooze` with `ticket_id` and `minutes=30`. Re-trigger immediately. Assert no new log rows appear until the snooze window expires.
5. Resolve the ticket (`UPDATE tickets SET resolved_at = ? WHERE id = ?`). Re-trigger. Assert no new escalations are produced.

## Related

- `workers-github-issue-triage-bot.md` — SLA tracking for GitHub issue response time
- `workers-change-failure-rate-tracker.md` — DORA metrics including incident linkage
- `workers-postmortem-generator.md` — postmortem generation triggered after breach

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://developer.pagerduty.com/api-reference/368ae3d938c9e-send-an-event-to-pager-duty
- https://api.slack.com/messaging/webhooks
