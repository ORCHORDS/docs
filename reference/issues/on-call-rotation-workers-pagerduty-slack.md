# On-call Rotation Management Worker with PagerDuty and Slack

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your team rotates on-call weekly and needs a central Worker that answers `/oncall` Slack slash commands, creates PagerDuty incidents from Worker routes, and sends handoff notifications 1 hour before each shift change via Cron — all without a dedicated backend server. The schedule lives in D1 so rotations are easy to update via API.

---

## Context
A D1 `on_call_schedules` table stores weekly rotation entries keyed by ISO week number. The Worker exposes three surfaces: a Slack slash-command endpoint (`/slack/oncall`) that looks up and returns the current on-call person, a PagerDuty trigger endpoint (`/pagerduty/incident`) that creates an incident via PagerDuty Events API v2, and a Cron handler (`0 * * * *`) that fires every hour, checks whether a handoff occurs in the next 60 minutes, and sends a Slack notification to both the outgoing and incoming engineers. The rotation is deterministic — week index modulo team size — so no external scheduling service is needed.

---

## Section 1 — D1 Schema & wrangler.toml

```sql
CREATE TABLE IF NOT EXISTS on_call_schedules (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  year         INTEGER NOT NULL,
  week_number  INTEGER NOT NULL,   -- ISO week 1-53
  engineer     TEXT    NOT NULL,   -- Slack user ID e.g. U012AB3CD
  display_name TEXT    NOT NULL,
  email        TEXT    NOT NULL,
  pd_user_id   TEXT,               -- PagerDuty user ID for escalation
  UNIQUE (year, week_number)
);

-- Seed example (year 2026, weeks 1-4)
INSERT OR IGNORE INTO on_call_schedules (year, week_number, engineer, display_name, email, pd_user_id)
VALUES
  (2026, 34, 'U012AB3CD', 'Alice', 'alice@example.com', 'PUJ1A2B'),
  (2026, 35, 'U023BC4DE', 'Bob',   'bob@example.com',   'PVK2B3C'),
  (2026, 36, 'U034CD5EF', 'Carol', 'carol@example.com', 'PWL3C4D'),
  (2026, 37, 'U012AB3CD', 'Alice', 'alice@example.com', 'PUJ1A2B');

CREATE INDEX IF NOT EXISTS idx_ocs_week ON on_call_schedules (year, week_number);
```

```toml
# wrangler.toml
name = "oncall-manager"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[triggers]
crons = ["0 * * * *"]   # every hour

[[d1_databases]]
binding    = "DB"
database_name = "oncall-db"
database_id   = "<your-d1-id>"

[vars]
SLACK_WEBHOOK          = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
PAGERDUTY_ROUTING_KEY  = "<32-char-integration-key>"
SLACK_SIGNING_SECRET   = ""   # set via wrangler secret
```

---

## Section 2 — Main Worker request router

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  SLACK_WEBHOOK: string;
  PAGERDUTY_ROUTING_KEY: string;
  SLACK_SIGNING_SECRET: string;  // Worker secret
}

interface OnCallRow {
  engineer: string;
  display_name: string;
  email: string;
  pd_user_id: string | null;
  year: number;
  week_number: number;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/slack/oncall' && request.method === 'POST') {
      return handleSlashCommand(request, env);
    }
    if (url.pathname === '/pagerduty/incident' && request.method === 'POST') {
      return handlePagerDutyIncident(request, env);
    }
    if (url.pathname === '/oncall/schedule' && request.method === 'GET') {
      return handleGetSchedule(env, url.searchParams);
    }
    if (url.pathname === '/oncall/schedule' && request.method === 'POST') {
      return handleUpsertSchedule(request, env);
    }
    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(checkHandoff(env));
  },
};

function isoWeek(date: Date): { year: number; week: number } {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return { year: d.getUTCFullYear(), week };
}

async function getCurrentOnCall(env: Env, date?: Date): Promise<OnCallRow | null> {
  const { year, week } = isoWeek(date ?? new Date());
  return env.DB.prepare(
    `SELECT * FROM on_call_schedules WHERE year = ? AND week_number = ?`
  ).bind(year, week).first<OnCallRow>();
}

async function handleGetSchedule(env: Env, params: URLSearchParams): Promise<Response> {
  const weeks = parseInt(params.get('weeks') ?? '4', 10);
  const rows = await env.DB.prepare(
    `SELECT * FROM on_call_schedules ORDER BY year DESC, week_number DESC LIMIT ?`
  ).bind(weeks).all<OnCallRow>();
  return new Response(JSON.stringify(rows.results), {
    headers: { 'Content-Type': 'application/json' },
  });
}

async function handleUpsertSchedule(request: Request, env: Env): Promise<Response> {
  const body = await request.json() as Partial<OnCallRow>;
  const { year, week_number, engineer, display_name, email, pd_user_id } = body;
  if (!year || !week_number || !engineer || !display_name || !email) {
    return new Response(JSON.stringify({ error: 'year, week_number, engineer, display_name, email required' }), { status: 400 });
  }
  await env.DB.prepare(
    `INSERT INTO on_call_schedules (year, week_number, engineer, display_name, email, pd_user_id)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT (year, week_number) DO UPDATE SET
       engineer = excluded.engineer,
       display_name = excluded.display_name,
       email = excluded.email,
       pd_user_id = excluded.pd_user_id`
  ).bind(year, week_number, engineer, display_name, email, pd_user_id ?? null).run();
  return new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } });
}
```

---

## Section 3 — Slack slash command, PagerDuty trigger, and Cron handoff

```typescript
async function handleSlashCommand(request: Request, env: Env): Promise<Response> {
  // Slack sends application/x-www-form-urlencoded
  const body = await request.text();
  // Verify Slack signature (simplified — use full HMAC check in production)
  const params = new URLSearchParams(body);
  const _userId = params.get('user_id');

  const onCall = await getCurrentOnCall(env);
  if (!onCall) {
    return Response.json({ response_type: 'ephemeral', text: 'No on-call schedule found for this week.' });
  }

  const { year, week } = isoWeek(new Date());
  return Response.json({
    response_type: 'in_channel',
    text: `*On-call for week ${week}/${year}:* <@${onCall.engineer}> (${onCall.display_name}) — ${onCall.email}`,
  });
}

async function handlePagerDutyIncident(
  request: Request,
  env: Env
): Promise<Response> {
  const { summary, source, severity } = await request.json() as {
    summary: string;
    source: string;
    severity?: 'critical' | 'error' | 'warning' | 'info';
  };

  const onCall = await getCurrentOnCall(env);

  const pdPayload = {
    routing_key: env.PAGERDUTY_ROUTING_KEY,
    event_action: 'trigger',
    payload: {
      summary,
      source,
      severity: severity ?? 'error',
      custom_details: {
        on_call_engineer: onCall?.display_name ?? 'Unknown',
        on_call_email: onCall?.email ?? 'Unknown',
      },
    },
  };

  const res = await fetch('https://events.pagerduty.com/v2/enqueue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(pdPayload),
  });

  const result = await res.json() as { dedup_key?: string; status?: string };

  if (!res.ok) {
    return Response.json({ error: 'PagerDuty enqueue failed', detail: result }, { status: 502 });
  }

  return Response.json({ ok: true, dedup_key: result.dedup_key });
}

async function checkHandoff(env: Env): Promise<void> {
  const now = new Date();
  const inOneHour = new Date(now.getTime() + 60 * 60 * 1000);

  const { year: yearNow, week: weekNow } = isoWeek(now);
  const { year: yearNext, week: weekNext } = isoWeek(inOneHour);

  // No handoff if both hours are in the same ISO week
  if (yearNow === yearNext && weekNow === weekNext) return;

  const [outgoing, incoming] = await Promise.all([
    env.DB.prepare(`SELECT * FROM on_call_schedules WHERE year = ? AND week_number = ?`)
      .bind(yearNow, weekNow).first<OnCallRow>(),
    env.DB.prepare(`SELECT * FROM on_call_schedules WHERE year = ? AND week_number = ?`)
      .bind(yearNext, weekNext).first<OnCallRow>(),
  ]);

  if (!outgoing || !incoming) return;

  await fetch(env.SLACK_WEBHOOK, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: 'On-call rotation handoff in 1 hour',
      blocks: [
        {
          type: 'header',
          text: { type: 'plain_text', text: 'On-call Handoff — 1 hour notice' },
        },
        {
          type: 'section',
          fields: [
            { type: 'mrkdwn', text: `*Outgoing:*\n<@${outgoing.engineer}> (${outgoing.display_name})` },
            { type: 'mrkdwn', text: `*Incoming:*\n<@${incoming.engineer}> (${incoming.display_name})` },
          ],
        },
        {
          type: 'context',
          elements: [{ type: 'mrkdwn', text: `Shift handoff at Monday 00:00 UTC | Week ${weekNext}/${yearNext}` }],
        },
      ],
    }),
  });
}
```

---

## Anti-patterns
- **Storing the rotation only in Worker code** — a hardcoded array is uneditable without redeployment; use D1 so rotations are API-updateable.
- **Skipping Slack signature verification** — always verify the `X-Slack-Signature` HMAC in production to prevent spoofed slash commands.
- **Firing handoff notifications every hour when there is no handoff** — check whether the ISO week changes within the next 60 minutes before sending.
- **Creating PagerDuty incidents directly from Cron** — incidents should be created in response to real events (explicit API call), not on a schedule.

---

## Gotchas
- ISO week numbers differ from calendar week numbers — use the `isoWeek()` helper above, not `getDay()` / `getWeek()` shims.
- PagerDuty Events API v2 (`/v2/enqueue`) accepts `routing_key`, not `service_key` — the older v1 key format will be rejected.
- Slack slash-command payloads are `application/x-www-form-urlencoded`, not JSON — parse with `URLSearchParams`.
- The Cron fires every hour at :00 UTC; the handoff check window is Monday 00:00 UTC — the notification fires at Sunday 23:00 UTC (one hour before).
- D1 `ON CONFLICT ... DO UPDATE SET` requires the `UNIQUE` constraint to exist; verify with `.schema` before inserting.

---

## Verification
```bash
# Deploy
npx wrangler deploy
npx wrangler secret put SLACK_SIGNING_SECRET
npx wrangler secret put PAGERDUTY_ROUTING_KEY

# Seed the schedule
npx wrangler d1 execute oncall-db --file=schema.sql

# Test slash command (simulate Slack POST)
curl -X POST https://<worker>.workers.dev/slack/oncall \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'user_id=U012AB3CD&command=/oncall'

# Trigger a PagerDuty incident
curl -X POST https://<worker>.workers.dev/pagerduty/incident \
  -H 'Content-Type: application/json' \
  -d '{"summary":"DB connection pool exhausted","source":"workers-api","severity":"critical"}'

# Test the Cron handoff check
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"

# View current on-call
curl https://<worker>.workers.dev/oncall/schedule?weeks=2
```

---

## Related
- `incident-postmortem-d1-workers-template.md`
- `github-issue-sla-breach-cron-workers.md`

---

## Sources
- PagerDuty Events API v2 — https://developer.pagerduty.com/docs/events-api-v2/overview/
- Slack slash commands — https://api.slack.com/interactivity/slash-commands
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
