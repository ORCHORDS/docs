# Email Timezone-Aware Send Scheduling with Workers Cron and D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A broadcast sent at 09:00 UTC arrives at 01:00 for subscribers in Sydney and
17:00 the previous day for San Francisco. Open rates tank for non-UTC segments.
You need each subscriber to receive the email at their local 09:00 regardless of
where they are, without running 24 separate scheduler jobs.

## Context

Subscribers store a UTC offset (or IANA timezone name) in D1. A cron Worker fires
every 15 minutes, queries for subscribers whose local time window matches the
target send hour, and enqueues them in batches. Sends are staggered naturally
across the day as time zones roll through the target window. D1 handles the
scheduling state; Cloudflare Queues handle the actual delivery pipeline.

## D1 Schema

```sql
-- Extend subscribers table
ALTER TABLE subscribers ADD COLUMN tz_offset_minutes INTEGER NOT NULL DEFAULT 0;
-- e.g. UTC+5:30 = 330, UTC-8 = -480

-- Scheduled campaigns table
CREATE TABLE IF NOT EXISTS campaigns_scheduled (
  id           TEXT PRIMARY KEY,
  subject      TEXT NOT NULL,
  html         TEXT NOT NULL,
  target_hour  INTEGER NOT NULL CHECK (target_hour BETWEEN 0 AND 23),
  target_minute INTEGER NOT NULL DEFAULT 0,
  window_minutes INTEGER NOT NULL DEFAULT 15,  -- tolerance
  send_date    TEXT NOT NULL,   -- 'YYYY-MM-DD' in UTC
  status       TEXT NOT NULL DEFAULT 'pending',  -- pending | sending | done
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Sent log to prevent double-sends
CREATE TABLE IF NOT EXISTS campaign_sends (
  campaign_id  TEXT NOT NULL,
  subscriber_id TEXT NOT NULL,
  enqueued_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (campaign_id, subscriber_id)
);
```

## Subscriber Timezone Resolution

```typescript
// src/tz-utils.ts
/**
 * Returns true if the subscriber's local time is within the target window.
 * @param utcNowMinutes - current UTC time in minutes since midnight
 * @param tzOffsetMinutes - subscriber UTC offset in minutes (e.g. 330 for UTC+5:30)
 * @param targetHour - desired local hour (0-23)
 * @param targetMinute - desired local minute (0-59)
 * @param windowMinutes - tolerance window in minutes
 */
export function isInSendWindow(
  utcNowMinutes: number,
  tzOffsetMinutes: number,
  targetHour: number,
  targetMinute: number,
  windowMinutes: number
): boolean {
  const localMinutes = ((utcNowMinutes + tzOffsetMinutes) % 1440 + 1440) % 1440;
  const targetMinutes = targetHour * 60 + targetMinute;
  const diff = Math.abs(localMinutes - targetMinutes);
  // Handle day boundary wrap (e.g. 23:55 vs 00:05)
  return Math.min(diff, 1440 - diff) < windowMinutes;
}
```

## Cron Worker: Per-tick Subscriber Selection and Enqueue

```typescript
// src/scheduler.ts
import { isInSendWindow } from "./tz-utils";

interface Env {
  DB: D1Database;
  Q_BULK: Queue<{ campaign_id: string; subscriber_id: string;
                  to: string; subject: string; html: string }>;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const now = new Date(event.scheduledTime);
    const utcNowMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
    const todayDate = now.toISOString().slice(0, 10);

    // Fetch all pending campaigns for today
    const campaigns = await env.DB
      .prepare(
        `SELECT * FROM campaigns_scheduled
         WHERE status = 'pending' AND send_date = ?`
      )
      .bind(todayDate)
      .all<{
        id: string; subject: string; html: string;
        target_hour: number; target_minute: number; window_minutes: number;
      }>();

    for (const campaign of campaigns.results) {
      // Find subscribers in the current send window not yet enqueued
      const subscribers = await env.DB
        .prepare(
          `SELECT s.id, s.email, s.tz_offset_minutes
           FROM subscribers s
           WHERE s.active = 1
             AND NOT EXISTS (
               SELECT 1 FROM campaign_sends cs
               WHERE cs.campaign_id = ? AND cs.subscriber_id = s.id
             )
           ORDER BY s.id`
        )
        .bind(campaign.id)
        .all<{ id: string; email: string; tz_offset_minutes: number }>();

      const batch: Parameters<typeof env.Q_BULK.sendBatch>[0] = [];

      for (const sub of subscribers.results) {
        if (
          isInSendWindow(
            utcNowMinutes,
            sub.tz_offset_minutes,
            campaign.target_hour,
            campaign.target_minute,
            campaign.window_minutes
          )
        ) {
          batch.push({
            body: {
              campaign_id: campaign.id,
              subscriber_id: sub.id,
              to: sub.email,
              subject: campaign.subject,
              html: campaign.html,
            },
          });
        }
      }

      if (batch.length > 0) {
        // Record sends atomically before enqueue to prevent double-enqueue
        const inserts = batch
          .map(() => "(?, ?)")
          .join(", ");
        const values = batch.flatMap((m) => [
          m.body.campaign_id,
          m.body.subscriber_id,
        ]);
        await env.DB
          .prepare(
            `INSERT OR IGNORE INTO campaign_sends (campaign_id, subscriber_id)
             VALUES ${inserts}`
          )
          .bind(...values)
          .run();

        await env.Q_BULK.sendBatch(batch);
      }
    }
  },
};
```

`wrangler.toml` cron: `crons = ["*/15 * * * *"]`

## Campaign Completion Marking (Cron or Webhook)

```typescript
// Mark a campaign done when all subscribers have been processed
async function markDoneIfComplete(db: D1Database, campaignId: string): Promise<void> {
  const remaining = await db
    .prepare(
      `SELECT COUNT(*) AS cnt FROM subscribers s
       WHERE s.active = 1
         AND NOT EXISTS (
           SELECT 1 FROM campaign_sends cs
           WHERE cs.campaign_id = ? AND cs.subscriber_id = s.id
         )`
    )
    .bind(campaignId)
    .first<{ cnt: number }>();

  if ((remaining?.cnt ?? 1) === 0) {
    await db
      .prepare("UPDATE campaigns_scheduled SET status = 'done' WHERE id = ?")
      .bind(campaignId)
      .run();
  }
}
```

## Timezone Offset Population

```typescript
// src/register-subscriber.ts  (excerpt)
// Accept IANA timezone name from signup form, convert to offset minutes
async function tzNameToOffsetMinutes(tzName: string): Promise<number> {
  // Use Intl.DateTimeFormat to determine current offset
  const now = new Date();
  const formatter = new Intl.DateTimeFormat("en", {
    timeZone: tzName,
    timeZoneName: "shortOffset",
  });
  const parts = formatter.formatToParts(now);
  const offsetPart = parts.find((p) => p.type === "timeZoneName")?.value ?? "UTC+0";
  const match = offsetPart.match(/UTC([+-])(\d{1,2}):?(\d{0,2})/);
  if (!match) return 0;
  const sign = match[1] === "+" ? 1 : -1;
  const hours = parseInt(match[2], 10);
  const minutes = parseInt(match[3] || "0", 10);
  return sign * (hours * 60 + minutes);
}
```

## Anti-patterns

- **Single cron at midnight UTC** – this sends all subscribers at the same moment
  regardless of their timezone; you need sub-hourly cron resolution (15 min).
- **Not recording sends before enqueue** – on cron overlap or re-trigger, the same
  subscriber is enqueued twice; the `INSERT OR IGNORE` guard is essential.
- **Storing IANA timezone names and doing JS tz math in the query** – D1 has no
  `CONVERT_TZ`; pre-compute the UTC offset at registration time and store it as an
  integer for fast SQL filtering.

## Gotchas

- DST changes shift UTC offsets twice a year; `tz_offset_minutes` becomes stale for
  affected zones unless refreshed. Consider storing the IANA name separately and
  recomputing the offset at the start of each campaign.
- Workers Cron fires are best-effort; a missed 15-minute tick shifts affected
  subscribers' delivery by one window. Set `window_minutes = 20` to absorb drift.
- Subscribers with unusual half-hour or 45-minute offsets (India UTC+5:30,
  Nepal UTC+5:45) require the modular arithmetic in `isInSendWindow` to be
  correct; test these edge cases explicitly.

## Verification

```sql
-- Check how many subscribers are in each 15-min UTC window for a 09:00 local send
SELECT
  (tz_offset_minutes / 60) AS utc_offset_hour,
  COUNT(*) AS subscribers,
  -- local 09:00 = UTC (9*60 - tz_offset_minutes) mod 1440
  MOD(540 - tz_offset_minutes + 1440, 1440) / 60 AS utc_send_hour
FROM subscribers
WHERE active = 1
GROUP BY utc_offset_hour
ORDER BY utc_send_hour;
```

```bash
# Tail cron Worker logs to confirm per-tick enqueue counts
wrangler tail scheduler --env production --format pretty
```

## Related

- `email-send-time-optimization-analytics-engine.md`
- `email-scheduling-patterns.md`
- `email-drip-campaign-sequence-queues-workers.md`
- `email-batch-sending.md`

## Sources

- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare Queues sendBatch: https://developers.cloudflare.com/queues/reference/javascript-apis/#queuesendmessages
- IANA Time Zone Database: https://www.iana.org/time-zones
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
