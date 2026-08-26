# On-Call Handoff Automation Bot in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

On-call rotations suffer from incomplete handoffs: the outgoing engineer forgets to mention a flapping alert, a pending SLA breach, or an open incident that the incoming engineer discovers hours later — after the breach has already occurred. Manual handoff Slack messages are inconsistent and often written in a hurry.

## Context

A scheduled Cloudflare Worker fires at handoff time (typically every 7 days, or at shift boundary), queries D1 for open incidents, pending alerts, and SLA status, formats a structured Slack message, and posts it to the on-call channel. If the incoming on-call engineer does not acknowledge within 30 minutes, the Worker escalates to a manager. Acknowledgment is recorded via a Slack interactive component callback.

Prerequisites:
- D1 database bound as `DB` (populated by other Workers in this series)
- KV namespace bound as `HANDOFF_STATE` (acknowledgment tracking)
- Secrets: `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_ESCALATION_CHANNEL_ID`
- Cron trigger configured for handoff schedule (e.g., `0 9 * * MON`)

## Solution

```typescript
// worker-handoff-bot.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  HANDOFF_STATE: KVNamespace;
  SLACK_BOT_TOKEN: string;
  SLACK_CHANNEL_ID: string;
  SLACK_ESCALATION_CHANNEL_ID: string;
  SLACK_SIGNING_SECRET: string;
}

interface OpenIncident {
  id: string;
  title: string;
  started_at: number;
  severity: string;
}

interface PendingAlert {
  alert_id: string;
  service: string;
  severity: string;
  fired_at: number;
}

interface SlaStatus {
  service: string;
  error_budget_remaining_pct: number;
  next_breach_at: number | null;
}

async function slackPost(token: string, channel: string, blocks: unknown[], text: string) {
  const res = await fetch('https://slack.com/api/chat.postMessage', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ channel, text, blocks }),
  });
  const data = await res.json<{ ok: boolean; ts: string; error?: string }>();
  if (!data.ok) throw new Error(`Slack error: ${data.error}`);
  return data.ts;
}

async function buildHandoffSummary(env: Env): Promise<{
  incidents: OpenIncident[];
  alerts: PendingAlert[];
  sla: SlaStatus[];
}> {
  const [incidentsRes, alertsRes, slaRes] = await Promise.all([
    env.DB.prepare(`
      SELECT id, title, started_at, severity
      FROM incidents
      WHERE resolved_at IS NULL
      ORDER BY started_at ASC
    `).all<OpenIncident>(),

    env.DB.prepare(`
      SELECT alert_id, service, severity, alert_fired_at AS fired_at
      FROM mttd_records
      WHERE created_at >= ?
      ORDER BY alert_fired_at DESC
      LIMIT 20
    `).bind(Date.now() - 24 * 3_600_000).all<PendingAlert>(),

    env.DB.prepare(`
      SELECT service, error_budget_remaining_pct, next_breach_at
      FROM slo_status
      WHERE error_budget_remaining_pct < 20
      ORDER BY error_budget_remaining_pct ASC
    `).all<SlaStatus>(),
  ]);

  return {
    incidents: incidentsRes.results,
    alerts: alertsRes.results,
    sla: slaRes.results,
  };
}

function formatHandoffBlocks(
  summary: Awaited<ReturnType<typeof buildHandoffSummary>>,
  handoffId: string
): unknown[] {
  const { incidents, alerts, sla } = summary;
  const now = new Date().toISOString();

  const incidentSection = incidents.length === 0
    ? ':white_check_mark: No open incidents'
    : incidents.map(i =>
        `:fire: *${i.title}* — open since <!date^${Math.floor(i.started_at / 1000)}^{date_short_pretty} at {time}|${new Date(i.started_at).toISOString()}>`
      ).join('\n');

  const slaSection = sla.length === 0
    ? ':white_check_mark: All services healthy'
    : sla.map(s =>
        `:warning: *${s.service}* — ${s.error_budget_remaining_pct.toFixed(1)}% budget remaining` +
        (s.next_breach_at ? ` (breach at <!date^${Math.floor(s.next_breach_at / 1000)}^{time}|soon>)` : '')
      ).join('\n');

  return [
    {
      type: 'header',
      text: { type: 'plain_text', text: `:pager: On-Call Handoff — ${now.slice(0, 10)}` },
    },
    { type: 'divider' },
    {
      type: 'section',
      text: { type: 'mrkdwn', text: `*Open Incidents (${incidents.length})*\n${incidentSection}` },
    },
    {
      type: 'section',
      text: { type: 'mrkdwn', text: `*SLA Risk (${sla.length} services)*\n${slaSection}` },
    },
    {
      type: 'section',
      text: { type: 'mrkdwn', text: `*Alerts in last 24h:* ${alerts.length} fired` },
    },
    { type: 'divider' },
    {
      type: 'actions',
      block_id: `handoff_ack:${handoffId}`,
      elements: [
        {
          type: 'button',
          text: { type: 'plain_text', text: 'Acknowledge Handoff' },
          style: 'primary',
          action_id: 'ack_handoff',
          value: handoffId,
        },
      ],
    },
  ];
}

const app = new Hono<{ Bindings: Env }>();

// Slack interactive component callback (acknowledgment)
app.post('/slack/interact', async (c) => {
  const body = await c.req.text();
  // Verify Slack signature (simplified — use a proper HMAC in production)
  const payload = JSON.parse(new URLSearchParams(body).get('payload') ?? '{}');
  const action = payload?.actions?.[0];
  if (action?.action_id !== 'ack_handoff') return c.text('', 200);

  const handoffId = action.value as string;
  const engineer = payload.user?.name ?? 'unknown';

  await c.env.HANDOFF_STATE.put(
    `handoff:${handoffId}:ack`,
    JSON.stringify({ engineer, ackedAt: new Date().toISOString() }),
    { expirationTtl: 7 * 86_400 }
  );

  // Update the Slack message to show acknowledgment
  await fetch('https://slack.com/api/chat.update', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${c.env.SLACK_BOT_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      channel: payload.channel.id,
      ts: payload.message.ts,
      text: `:white_check_mark: Handoff acknowledged by @${engineer}`,
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `:white_check_mark: Handoff acknowledged by *@${engineer}* at ${new Date().toISOString().slice(0, 19)}Z`,
          },
        },
      ],
    }),
  });

  return c.text('', 200);
});

// Manual trigger endpoint
app.post('/handoff/trigger', async (c) => {
  await runHandoff(c.env);
  return c.json({ ok: true });
});

async function runHandoff(env: Env) {
  const handoffId = `handoff-${Date.now()}`;
  const summary = await buildHandoffSummary(env);
  const blocks = formatHandoffBlocks(summary, handoffId);
  const ts = await slackPost(
    env.SLACK_BOT_TOKEN,
    env.SLACK_CHANNEL_ID,
    blocks,
    'On-call handoff summary — please acknowledge.'
  );

  // Store handoff metadata for escalation check
  await env.HANDOFF_STATE.put(
    `handoff:${handoffId}:meta`,
    JSON.stringify({ ts, channel: env.SLACK_CHANNEL_ID, sentAt: Date.now() }),
    { expirationTtl: 7 * 86_400 }
  );
}

export default {
  fetch: app.fetch,

  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    if (event.cron === '0 9 * * MON') {
      // Handoff trigger
      await runHandoff(env);
    } else if (event.cron === '30 9 * * MON') {
      // Escalation check: 30 minutes after handoff
      const keys = await env.HANDOFF_STATE.list({ prefix: 'handoff:' });
      for (const key of keys.keys) {
        if (!key.name.endsWith(':meta')) continue;
        const handoffId = key.name.replace('handoff:', '').replace(':meta', '');
        const ackRaw = await env.HANDOFF_STATE.get(`handoff:${handoffId}:ack`);
        if (ackRaw) continue; // already acknowledged

        const metaRaw = await env.HANDOFF_STATE.get(key.name);
        if (!metaRaw) continue;
        const meta = JSON.parse(metaRaw);
        if (Date.now() - meta.sentAt < 30 * 60_000) continue; // too soon

        // Escalate
        await slackPost(
          env.SLACK_BOT_TOKEN,
          env.SLACK_ESCALATION_CHANNEL_ID,
          [
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: `:rotating_light: On-call handoff *${handoffId}* was NOT acknowledged within 30 minutes. Please verify coverage.`,
              },
            },
          ],
          'ESCALATION: On-call handoff unacknowledged'
        );
      }
    }
  },
};
```

## Implementation Details

- **Two cron expressions**: `0 9 * * MON` fires the handoff message; `30 9 * * MON` fires the escalation check. Both are registered in `wrangler.toml` under `[triggers] crons`.
- **KV TTL**: Handoff metadata expires after 7 days to avoid unbounded growth. The list-and-scan pattern for escalation checks is acceptable for a once-weekly check with a small key count.
- **SLO data source**: `slo_status` table assumed to be populated by the error-budget tracker Worker. If the table does not exist yet, initialize it with `CREATE TABLE IF NOT EXISTS slo_status (...)`.
- **Slack block kit**: The acknowledgment button carries the `handoffId` as its `value`. The interactive callback endpoint updates the original message in-place using `chat.update`.
- **Signature verification**: The `/slack/interact` route needs proper HMAC-SHA256 signature verification using `SLACK_SIGNING_SECRET`. The skeleton above omits it for brevity — add it before deploying to production.

## Anti-patterns

- **Sending a plain-text handoff message**: Block Kit with explicit sections and an acknowledgment button creates accountability. Plain text is unstructured, unscannable, and offers no interaction surface.
- **Polling D1 at interaction time**: Pre-compute the handoff summary at cron time. Do not query D1 inside the Slack interactive callback — it adds latency to a response that Slack expects within 3 seconds.
- **Using a single cron for handoff + escalation**: If the cron is delayed by cold start, the 30-minute window blurs. Two separate cron entries give independent retry surfaces.
- **Storing acknowledgment in D1**: KV is correct here — acknowledgments are ephemeral session state, not business records. D1 is for the incident and alert data that the handoff summary reads.

## Gotchas

- Slack's interactive payload arrives as `application/x-www-form-urlencoded` with a `payload` key containing JSON. Do not attempt to parse it directly as JSON with `c.req.json()`.
- `HANDOFF_STATE.list()` returns a maximum of 1000 keys per call. If your rotation generates more than 1000 unacknowledged handoffs (an alarming operational state), paginate with the `cursor` returned by `list()`.
- The Slack `<!date^...^...>` formatting renders timestamps in the viewer's local timezone — essential for distributed teams but requires the Unix timestamp in seconds, not milliseconds. Divide `happenedAt` by 1000.
- Workers with multiple cron triggers must handle them in the `scheduled` handler via `event.cron` matching. Failing to match means the wrong logic runs at the wrong time.

## Verification

```bash
# 1. Manually trigger handoff (check Slack #on-call channel)
curl -X POST https://handoff-bot.example.workers.dev/handoff/trigger

# 2. Simulate acknowledgment (mimic Slack interactive payload)
curl -X POST https://handoff-bot.example.workers.dev/slack/interact \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'payload={"actions":[{"action_id":"ack_handoff","value":"handoff-TEST"}],"user":{"name":"alice"},"channel":{"id":"C123"},"message":{"ts":"111.222"}}'

# 3. Verify KV acknowledgment
wrangler kv key get --namespace-id=<NS_ID> 'handoff:handoff-TEST:ack'
# Expected: {"engineer":"alice","ackedAt":"..."}

# 4. Test escalation path by not acknowledging and checking escalation channel after 30m
# (in staging, reduce escalation window to 1 minute for faster iteration)
```

## Related

- `documentation/docs/policies/issues/workers-sla-breach-auto-escalation.md` — feeds SLA risk data into handoff summaries
- `documentation/docs/policies/issues/workers-incident-response-bot.md` — incident records queried during handoff summary generation
- `documentation/docs/policies/issues/workers-error-budget-tracker.md` — populates the `slo_status` table consumed here
- `documentation/docs/policies/issues/workers-alert-correlation-dedup.md` — alert records in the 24-hour window displayed in handoff

## Sources

- [Cloudflare Workers Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
- [Slack Block Kit Reference](https://api.slack.com/block-kit)
- [Slack Interactive Components](https://api.slack.com/interactivity/handling)
- [Cloudflare KV API](https://developers.cloudflare.com/kv/api/)
