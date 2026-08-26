# Newsletter Subscriber Segmentation Engine with D1 and Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Dynamic Newsletter Segmentation at the Edge

Blast-to-list email is dead. Subscribers who receive irrelevant content
unsubscribe or mark as spam; senders who personalise based on behaviour and
preference see 2-3× higher open rates and significantly lower churn. Building
a behavioural segmentation engine requires a queryable subscriber store, a
flexible tagging model, and a send-time orchestration layer that can compose
segment queries on the fly.

D1 — Cloudflare's SQLite-at-the-edge database — is an excellent fit: it
supports full SQL, runs in the same isolate as Workers, and handles the
moderate write loads of a newsletter platform without a separate database
service. Workers Cron Triggers drive scheduled sends, while Analytics Engine
captures per-segment performance for continuous A/B optimisation of send
windows.

The architecture keeps subscriber PII inside D1, segment logic in SQL, and
rendering at the edge — no external data warehouse needed for lists under
~500 k subscribers.

## Context

Stack: Cloudflare Workers, D1, Analytics Engine, Queues, Resend or SendGrid,
TypeScript, Wrangler 3+.

Subscribers accumulate behavioural tags from product events forwarded via a
Workers ingest endpoint. A scheduled Worker queries D1 to build dynamic
segment membership, enqueues individual personalised sends, and a consumer
Worker dispatches via the configured ESP. Performance metrics land in
Analytics Engine for A/B send-time analysis.

## D1 Schema

```sql
-- migrations/0001_segmentation.sql

CREATE TABLE subscribers (
  id          TEXT PRIMARY KEY,           -- UUID
  email       TEXT UNIQUE NOT NULL,
  tz          TEXT NOT NULL DEFAULT 'UTC',
  created_at  INTEGER NOT NULL,
  unsubscribed_at INTEGER
);

CREATE TABLE tags (
  subscriber_id TEXT NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
  tag           TEXT NOT NULL,            -- e.g. 'plan:pro', 'opened:last30d'
  value         TEXT,                     -- optional scalar payload
  scored_at     INTEGER NOT NULL,
  PRIMARY KEY (subscriber_id, tag)
);

CREATE INDEX idx_tags_tag ON tags(tag);

CREATE TABLE campaigns (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  segment_sql TEXT NOT NULL,             -- parameterised WHERE clause fragment
  subject     TEXT NOT NULL,
  template_id TEXT NOT NULL,
  send_window_start INTEGER,             -- hour-of-day in subscriber local tz
  send_window_end   INTEGER,
  created_at  INTEGER NOT NULL
);

CREATE TABLE send_log (
  campaign_id   TEXT NOT NULL,
  subscriber_id TEXT NOT NULL,
  queued_at     INTEGER NOT NULL,
  status        TEXT NOT NULL DEFAULT 'queued',  -- queued|sent|failed
  esp_message_id TEXT,
  PRIMARY KEY (campaign_id, subscriber_id)
);
```

## Segment Query Builder Worker

```ts
// workers/segment-builder.ts
import { D1Database, Queue } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  SEND_QUEUE: Queue;
  EMAIL_EVENTS: AnalyticsEngineDataset;
}

interface SendJob {
  campaignId: string;
  subscriberId: string;
  email: string;
  templateId: string;
  subject: string;
}

export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    // Fetch active campaigns due to send
    const now = Math.floor(Date.now() / 1000);
    const campaigns = await env.DB.prepare(
      `SELECT * FROM campaigns WHERE send_window_start IS NULL
         OR (CAST(strftime('%H', 'now') AS INTEGER) BETWEEN send_window_start AND send_window_end)`
    ).all<{ id: string; segment_sql: string; subject: string; template_id: string }>();

    for (const campaign of campaigns.results) {
      // Dynamic segment: inject the campaign's segment_sql as a WHERE predicate
      const stmt = env.DB.prepare(
        `SELECT s.id, s.email
         FROM subscribers s
         JOIN tags t ON t.subscriber_id = s.id
         WHERE s.unsubscribed_at IS NULL
           AND NOT EXISTS (
             SELECT 1 FROM send_log sl
             WHERE sl.campaign_id = ? AND sl.subscriber_id = s.id
           )
           AND (${campaign.segment_sql})
         LIMIT 500`
      ).bind(campaign.id);

      const members = await stmt.all<{ id: string; email: string }>();

      const jobs: SendJob[] = members.results.map((m) => ({
        campaignId: campaign.id,
        subscriberId: m.id,
        email: m.email,
        templateId: campaign.template_id,
        subject: campaign.subject,
      }));

      if (jobs.length > 0) {
        await env.SEND_QUEUE.sendBatch(jobs.map((j) => ({ body: j })));

        // Track segment size in Analytics Engine for A/B analysis
        env.EMAIL_EVENTS.writeDataPoint({
          blobs: [campaign.id, 'segment_queued'],
          doubles: [jobs.length],
          indexes: [campaign.id],
        });
      }
    }
  },
};
```

## Queue Consumer and Performance Tracking

```ts
// workers/send-consumer.ts
interface Env {
  DB: D1Database;
  EMAIL_EVENTS: AnalyticsEngineDataset;
  RESEND_API_KEY: string;
}

export default {
  async queue(batch: MessageBatch<SendJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { campaignId, subscriberId, email, templateId, subject } = msg.body;

      try {
        const res = await fetch('https://api.resend.com/emails', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${env.RESEND_API_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            from: 'newsletter@example.com',
            to: email,
            subject,
            html: `<p>Template: ${templateId}</p>`, // replaced by rendering worker
          }),
        });

        const { id: espId } = await res.json<{ id: string }>();

        await env.DB.prepare(
          `UPDATE send_log SET status = 'sent', esp_message_id = ? WHERE campaign_id = ? AND subscriber_id = ?`
        ).bind(espId, campaignId, subscriberId).run();

        env.EMAIL_EVENTS.writeDataPoint({
          blobs: [campaignId, 'sent', subscriberId],
          doubles: [Date.now()],
          indexes: [campaignId],
        });

        msg.ack();
      } catch (err) {
        msg.retry();
      }
    }
  },
};
```

## A/B Send-Time Optimisation Query

```ts
// Analyse send-time performance from Analytics Engine
const sql = `
  SELECT
    toStartOfHour(fromUnixTimestamp64Milli(double1)) AS send_hour,
    blob1                                             AS campaign_id,
    count()                                           AS sends
  FROM EMAIL_EVENTS
  WHERE blob2 = 'sent'
    AND timestamp > now() - INTERVAL '30' DAY
  GROUP BY send_hour, campaign_id
  ORDER BY sends DESC
`;
// Join with open/click events (blob2 = 'open') to compute engagement by send hour
```

## Anti-patterns

- Storing segment definitions as application code instead of SQL stored in D1 — makes dynamic campaign creation impossible without a deploy
- Running full-table subscriber scans without indexes on the `tags` table
- Bypassing the Queue and calling the ESP synchronously from the cron job — any ESP timeout kills the whole batch
- Using KV for subscriber state — KV is unqueryable; D1 is required for segment filtering

## Gotchas

- D1 `LIMIT` applies per query; paginate with `OFFSET` or cursor-based `WHERE id > last_id` for lists > 500
- The `segment_sql` column contains raw SQL fragments — sanitise campaign inputs to prevent injection if campaigns are user-created
- Analytics Engine `double1` stores epoch milliseconds as a float; use `fromUnixTimestamp64Milli` in AE SQL, not `fromUnixTimestamp`
- Workers Queue batch size defaults to 10; set `max_batch_size = 100` in `wrangler.toml` for higher throughput

## Verification

```ts
// Confirm segment membership before send
const preview = await env.DB.prepare(
  `SELECT count(*) AS n FROM subscribers s
   JOIN tags t ON t.subscriber_id = s.id
   WHERE s.unsubscribed_at IS NULL AND (t.tag = 'plan:pro')`
).first<{ n: number }>();
console.assert((preview?.n ?? 0) > 0, 'Segment is empty — check tag ingestion');
```

## Related

- analytics-engine-email-tracking.md
- bounce-suppression-d1.md
- email-engagement-scoring-segmentation.md
- transactional-email-rate-limiting-workers.md
- sendgrid-resend-cloudflare-workers-integration.md

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://resend.com/docs/api-reference/emails/send-email
- https://www.litmus.com/blog/email-personalization-statistics/
