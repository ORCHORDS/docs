# Email Campaign Pause/Resume Based on Real-Time Deliverability Signals

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A broadcast campaign starts sending and within the first few thousand emails the
bounce rate climbs to 8% or spam complaints exceed 0.3%. Continuing the send
accelerates reputation damage. You need automated circuit-breaker logic that
halts the campaign, alerts the team, and resumes only after manual clearance or
after the signal normalises below threshold.

## Context

A Cloudflare Cron Worker polls deliverability metrics every 5 minutes during an
active campaign send. Metrics arrive from two sources: (1) ESP webhooks
(Resend/SendGrid event webhooks) writing to D1; (2) optional Google Postmaster
API. When a metric breaches a threshold the Worker flips the campaign status to
`paused` in D1. The Queue consumer Worker checks this status before processing
each message batch and skips when paused.

## D1 Schema

```sql
-- campaigns table (extends campaigns_scheduled if already present)
CREATE TABLE IF NOT EXISTS campaigns (
  id              TEXT PRIMARY KEY,
  status          TEXT NOT NULL DEFAULT 'pending',
  -- 'pending' | 'sending' | 'paused' | 'done' | 'cancelled'
  pause_reason    TEXT,
  bounce_count    INTEGER NOT NULL DEFAULT 0,
  complaint_count INTEGER NOT NULL DEFAULT 0,
  send_count      INTEGER NOT NULL DEFAULT 0,
  paused_at       TEXT,
  resumed_at      TEXT,
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS campaign_events (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  campaign_id  TEXT NOT NULL,
  event_type   TEXT NOT NULL,  -- 'sent' | 'bounce' | 'complaint' | 'open' | 'click'
  email        TEXT,
  recorded_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_events_campaign_type
  ON campaign_events (campaign_id, event_type);
```

## ESP Webhook Ingestion Worker

```typescript
// src/event-ingestion.ts
interface Env {
  DB: D1Database;
  WEBHOOK_SECRET: string;
}

interface ResendWebhookEvent {
  type: "email.sent" | "email.bounced" | "email.complained" | "email.opened" | "email.clicked";
  data: { email_id: string; to: string[]; tags?: Record<string, string> };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Validate Resend webhook signature (svix or raw HMAC)
    const sig = request.headers.get("svix-signature") ?? "";
    if (!sig) return new Response("missing signature", { status: 401 });

    const body = await request.text();
    const event: ResendWebhookEvent = JSON.parse(body);

    const campaignId = event.data.tags?.campaign_id;
    if (!campaignId) return new Response("no campaign_id tag", { status: 200 });

    const eventTypeMap: Record<string, string> = {
      "email.sent": "sent",
      "email.bounced": "bounce",
      "email.complained": "complaint",
      "email.opened": "open",
      "email.clicked": "click",
    };

    const mappedType = eventTypeMap[event.type];
    if (!mappedType) return new Response("ignored", { status: 200 });

    const recipientEmail = event.data.to[0] ?? null;

    await env.DB.prepare(
      `INSERT INTO campaign_events (campaign_id, event_type, email)
       VALUES (?, ?, ?)`
    )
      .bind(campaignId, mappedType, recipientEmail)
      .run();

    // Increment aggregate counter
    if (mappedType === "sent") {
      await env.DB.prepare(
        "UPDATE campaigns SET send_count = send_count + 1, updated_at = ? WHERE id = ?"
      ).bind(new Date().toISOString(), campaignId).run();
    } else if (mappedType === "bounce") {
      await env.DB.prepare(
        "UPDATE campaigns SET bounce_count = bounce_count + 1, updated_at = ? WHERE id = ?"
      ).bind(new Date().toISOString(), campaignId).run();
    } else if (mappedType === "complaint") {
      await env.DB.prepare(
        "UPDATE campaigns SET complaint_count = complaint_count + 1, updated_at = ? WHERE id = ?"
      ).bind(new Date().toISOString(), campaignId).run();
    }

    return new Response("ok");
  },
};
```

## Circuit Breaker Cron Worker

```typescript
// src/circuit-breaker.ts
interface Env {
  DB: D1Database;
  ALERT_WEBHOOK_URL: string;  // Slack or PagerDuty
}

interface Campaign {
  id: string;
  status: string;
  bounce_count: number;
  complaint_count: number;
  send_count: number;
}

const BOUNCE_RATE_THRESHOLD = 0.05;      // 5%
const COMPLAINT_RATE_THRESHOLD = 0.001;  // 0.1% (Google/Yahoo limit)
const MIN_SAMPLE_SIZE = 200;             // don't trip on tiny samples

async function alertTeam(
  webhookUrl: string,
  campaignId: string,
  reason: string
): Promise<void> {
  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `🚨 Campaign ${campaignId} paused: ${reason}`,
    }),
  });
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const campaigns = await env.DB
      .prepare("SELECT * FROM campaigns WHERE status = 'sending'")
      .all<Campaign>();

    for (const c of campaigns.results) {
      if (c.send_count < MIN_SAMPLE_SIZE) continue;

      const bounceRate = c.bounce_count / c.send_count;
      const complaintRate = c.complaint_count / c.send_count;

      let pauseReason: string | null = null;

      if (bounceRate >= BOUNCE_RATE_THRESHOLD) {
        pauseReason = `bounce_rate=${(bounceRate * 100).toFixed(2)}%`;
      } else if (complaintRate >= COMPLAINT_RATE_THRESHOLD) {
        pauseReason = `complaint_rate=${(complaintRate * 100).toFixed(3)}%`;
      }

      if (pauseReason) {
        await env.DB.prepare(
          `UPDATE campaigns
           SET status = 'paused',
               pause_reason = ?,
               paused_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
           WHERE id = ?`
        )
          .bind(pauseReason, c.id)
          .run();

        await alertTeam(env.ALERT_WEBHOOK_URL, c.id, pauseReason);
      }
    }
  },
};
```

`wrangler.toml` cron: `crons = ["*/5 * * * *"]`

## Queue Consumer: Pause-Aware Send

```typescript
// src/consumer.ts (excerpt — add status check at top of queue handler)
interface Env {
  DB: D1Database;
  RESEND_API_KEY: string;
}

interface EmailJob {
  campaign_id: string;
  to: string;
  subject: string;
  html: string;
}

export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const campaign = await env.DB
        .prepare("SELECT status FROM campaigns WHERE id = ?")
        .bind(msg.body.campaign_id)
        .first<{ status: string }>();

      if (campaign?.status === "paused" || campaign?.status === "cancelled") {
        // Requeue with delay; will be retried after manual resume
        msg.retry({ delaySeconds: 300 });
        continue;
      }

      try {
        await sendEmail(msg.body, env.RESEND_API_KEY);
        msg.ack();
      } catch {
        msg.retry({ delaySeconds: 60 });
      }
    }
  },
};

async function sendEmail(job: EmailJob, apiKey: string): Promise<void> {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: "news@example.com",
      to: job.to,
      subject: job.subject,
      html: job.html,
      tags: [{ name: "campaign_id", value: job.campaign_id }],
    }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}`);
}
```

## Manual Resume API

```typescript
// POST /campaigns/:id/resume
async function resumeCampaign(db: D1Database, campaignId: string): Promise<void> {
  await db.prepare(
    `UPDATE campaigns
     SET status = 'sending',
         pause_reason = NULL,
         resumed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
         updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
     WHERE id = ? AND status = 'paused'`
  ).bind(campaignId).run();
}
```

## Anti-patterns

- **Tripping the circuit breaker on small samples** – 10 bounces out of 100 sends
  is 10% but statistically insignificant; enforce `MIN_SAMPLE_SIZE` (200+).
- **Auto-resuming after a fixed timeout** – resume only after a human reviews the
  root cause; automated resume risks re-triggering the circuit breaker immediately.
- **Not tagging emails with campaign_id** – webhook events without a campaign tag
  cannot be attributed; always pass campaign context as an ESP tag or header.

## Gotchas

- Queue messages retried with `delaySeconds: 300` remain in the queue up to
  `max_retries`; if a campaign is paused for days, messages will exhaust retries
  and go to the dead-letter queue. Consider draining the queue on cancel.
- Resend complaint events are reported by feedback loops with up to 24-hour lag;
  the circuit breaker threshold should account for this latency by using rolling
  7-day rates in addition to per-campaign counters.
- Google Postmaster API complaint data is available only for high-volume domains
  and requires separate OAuth integration; the webhook-based approach above works
  for all sending volumes.

## Verification

```bash
# Simulate bounces to trip the breaker
for i in $(seq 1 15); do
  curl -X POST https://example.com/webhooks/resend \
    -H "Content-Type: application/json" \
    -d '{"type":"email.bounced","data":{"email_id":"'$i'","to":["b'$i'@test.com"],"tags":{"campaign_id":"camp_001"}}}'
done

# Check campaign status
wrangler d1 execute email-db --remote \
  --command "SELECT id, status, bounce_count, send_count, pause_reason FROM campaigns WHERE id='camp_001';"
```

## Related

- `email-bounce-storm-circuit-breaker-workers.md`
- `email-complaint-rate-monitoring-workers-analytics.md`
- `email-deliverability-monitoring-workers-logpush.md`
- `email-esp-failover-health-check-workers.md`
- `transactional-email-dead-letter-queue-workers.md`

## Sources

- Google/Yahoo bulk sender requirements (0.1% complaint threshold):
  https://support.google.com/mail/answer/81126
- Cloudflare Queues retry semantics: https://developers.cloudflare.com/queues/reference/configuration/
- Resend webhook events: https://resend.com/docs/dashboard/webhooks/introduction
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
