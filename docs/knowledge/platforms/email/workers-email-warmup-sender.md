# IP/Domain Warm-up Email Sending Schedule with Workers + Queues

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Sending from a new IP or domain at full volume immediately causes ISPs to block or bulk-folder your email. You need a gradual ramp-up schedule that starts at ~50 emails on day 1 and grows to 50,000+ by day 30, enforced automatically, with automatic pausing when bounce rates spike.

## Context

Cloudflare Workers + Queues provide a serverless send pipeline. A daily cron Worker computes the volume cap for the current warm-up day, stores it in KV, and enqueues messages from an engagement-positive recipient list. The Queue consumer Worker dequeues and sends via MailChannels, tracking bounce and delivery results in D1. A bounce-rate check pauses the warm-up automatically.

## Solution

### Warm-up Volume Schedule

```typescript
// src/warmup-schedule.ts
// Exponential ramp: 50 → ~50,000 over 30 days
export function getDayCap(day: number): number {
  if (day < 1)  return 0;
  if (day > 30) return 50_000;

  // Piecewise ramp matching ISP warm-up guidelines:
  const schedule: Record<number, number> = {
    1: 50,    2: 100,   3: 200,   4: 400,   5: 700,
    6: 1_000, 7: 1_500, 8: 2_000, 9: 3_000, 10: 4_000,
    11: 5_000, 12: 6_500, 13: 8_000, 14: 10_000,
    15: 12_000, 16: 14_000, 17: 16_500, 18: 19_000, 19: 22_000,
    20: 25_000, 21: 28_000, 22: 31_000, 23: 34_500, 24: 38_000,
    25: 41_000, 26: 44_000, 27: 46_500, 28: 48_000, 29: 49_000,
    30: 50_000,
  };
  return schedule[day] ?? 50_000;
}
```

### KV State Keys

```typescript
// src/warmup-kv.ts
import { Env } from './types';

const KEY_START_DATE    = 'warmup:start_date';   // ISO date string
const KEY_SENT_TODAY    = 'warmup:sent_today';   // number
const KEY_PAUSED        = 'warmup:paused';       // '1' | absent
const KEY_PAUSE_REASON  = 'warmup:pause_reason'; // string

export async function getWarmupDay(env: Env): Promise<number> {
  const start = await env.KV.get(KEY_START_DATE);
  if (!start) return 0;
  const diffMs  = Date.now() - new Date(start).getTime();
  return Math.floor(diffMs / 86_400_000) + 1;
}

export async function getSentToday(env: Env): Promise<number> {
  const v = await env.KV.get(KEY_SENT_TODAY);
  return v ? parseInt(v, 10) : 0;
}

export async function incrementSentToday(env: Env, n = 1): Promise<void> {
  const current = await getSentToday(env);
  // TTL of 86400s resets the counter automatically at midnight UTC
  await env.KV.put(KEY_SENT_TODAY, String(current + n), { expirationTtl: 86_400 });
}

export async function isPaused(env: Env): Promise<boolean> {
  return (await env.KV.get(KEY_PAUSED)) === '1';
}

export async function pauseWarmup(env: Env, reason: string): Promise<void> {
  await env.KV.put(KEY_PAUSED, '1');
  await env.KV.put(KEY_PAUSE_REASON, reason);
}

export async function resumeWarmup(env: Env): Promise<void> {
  await env.KV.delete(KEY_PAUSED);
  await env.KV.delete(KEY_PAUSE_REASON);
}

export async function initWarmup(env: Env): Promise<void> {
  const existing = await env.KV.get(KEY_START_DATE);
  if (!existing) {
    await env.KV.put(KEY_START_DATE, new Date().toISOString().slice(0, 10));
  }
}
```

### D1 Schema

```sql
-- migrations/0004_warmup.sql
CREATE TABLE IF NOT EXISTS warmup_recipients (
  email          TEXT PRIMARY KEY,
  engagement     TEXT NOT NULL DEFAULT 'positive', -- positive | neutral
  added_at       INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS warmup_sends (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  email          TEXT NOT NULL,
  warmup_day     INTEGER NOT NULL,
  sent_at        INTEGER NOT NULL DEFAULT (unixepoch()),
  status         TEXT NOT NULL DEFAULT 'sent', -- sent | bounced | delivered
  bounce_type    TEXT  -- hard | soft
);

CREATE INDEX IF NOT EXISTS idx_warmup_sends_day
  ON warmup_sends (warmup_day, status);
```

### Cron Worker – Daily Warm-up Enqueuer

```typescript
// src/warmup-enqueuer.ts
import { Env }            from './types';
import { getDayCap }      from './warmup-schedule';
import { getWarmupDay, getSentToday, isPaused, initWarmup, pauseWarmup } from './warmup-kv';

export default {
  // Cron: "0 9 * * *"  — fires daily at 09:00 UTC
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runWarmupCycle(env));
  },
};

async function runWarmupCycle(env: Env): Promise<void> {
  await initWarmup(env);

  if (await isPaused(env)) {
    console.log('Warm-up paused — skipping today');
    return;
  }

  const day        = await getWarmupDay(env);
  const cap        = getDayCap(day);
  const sentToday  = await getSentToday(env);
  const remaining  = cap - sentToday;

  if (remaining <= 0) {
    console.log(`Day ${day}: cap ${cap} already reached`);
    return;
  }

  // Check bounce rate before sending
  const bounceRate = await getBounceRate(env, day);
  if (bounceRate > 0.05) {  // > 5% hard bounce rate → pause
    await pauseWarmup(env, `Bounce rate ${(bounceRate * 100).toFixed(1)}% on day ${day}`);
    await notifyOps(env, `Warm-up PAUSED: bounce rate ${(bounceRate * 100).toFixed(1)}%`);
    return;
  }

  // Fetch positive-engagement recipients not yet sent to today
  const { results: recipients } = await env.DB.prepare(`
    SELECT r.email
    FROM   warmup_recipients r
    LEFT JOIN warmup_sends s
      ON s.email = r.email AND s.warmup_day = ?
    WHERE  r.engagement = 'positive'
      AND  s.id IS NULL
      AND  r.email NOT IN (
             SELECT email FROM warmup_sends WHERE bounce_type = 'hard'
           )
    LIMIT  ?
  `).bind(day, remaining).all<{ email: string }>();

  // Enqueue each recipient
  const messages = recipients.map(r => ({ body: { email: r.email, day } }));
  if (messages.length > 0) {
    await env.WARMUP_QUEUE.sendBatch(messages);
  }

  console.log(`Day ${day}: enqueued ${messages.length} of cap ${cap}`);
}

async function getBounceRate(env: Env, day: number): Promise<number> {
  // Look at the last 3 days to smooth out noise
  const { results } = await env.DB.prepare(`
    SELECT
      COUNT(*)                                               AS total,
      SUM(CASE WHEN status='bounced' AND bounce_type='hard'
               THEN 1 ELSE 0 END)                          AS hard_bounces
    FROM warmup_sends
    WHERE warmup_day BETWEEN ? AND ?
  `).bind(Math.max(1, day - 2), day).all<{ total: number; hard_bounces: number }>();

  const { total, hard_bounces } = results[0];
  return total > 0 ? hard_bounces / total : 0;
}

async function notifyOps(env: Env, message: string): Promise<void> {
  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: 'ops@example.com' }] }],
      from: { email: 'alerts@example.com', name: 'Warm-up Monitor' },
      subject: `[WARMUP ALERT] ${message}`,
      content: [{ type: 'text/plain', value: message }],
    }),
  });
}
```

### Queue Consumer – Send Worker

```typescript
// src/warmup-consumer.ts
import { Env }               from './types';
import { incrementSentToday } from './warmup-kv';

interface WarmupMessage {
  email: string;
  day:   number;
}

export default {
  async queue(batch: MessageBatch<WarmupMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await sendWarmupEmail(env, msg.body.email);

        await env.DB.prepare(`
          INSERT INTO warmup_sends (email, warmup_day, status)
          VALUES (?, ?, 'sent')
        `).bind(msg.body.email, msg.body.day).run();

        await incrementSentToday(env);
        msg.ack();
      } catch (err) {
        console.error(`Failed to send to ${msg.body.email}:`, err);
        msg.retry();
      }
    }
  },
};

async function sendWarmupEmail(env: Env, recipientEmail: string): Promise<void> {
  const payload = {
    personalizations: [{ to: [{ email: recipientEmail }] }],
    from: { email: 'hello@example.com', name: 'Orchords' },
    subject: 'Checking in from Orchords',
    content: [{
      type: 'text/html',
      value: `<p>Hi, we wanted to reach out and share what's new at Orchords.
               <a href="https://example.com/unsubscribe?e=${encodeURIComponent(recipientEmail)}">Unsubscribe</a></p>`,
    }],
  };

  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`MailChannels ${res.status}`);
}
```

### wrangler.toml

```toml
[[queues.producers]]
binding  = "WARMUP_QUEUE"
queue    = "warmup-send-queue"

[[queues.consumers]]
queue            = "warmup-send-queue"
max_batch_size   = 10
max_retries      = 3
deadLetterQueue  = "warmup-dlq"

[[kv_namespaces]]
binding = "KV"
id      = "<your-kv-id>"

[triggers]
crons = ["0 9 * * *"]
```

## Implementation Details

- **KV TTL of 86,400 s** on the `sent_today` counter means it auto-resets at the natural expiry, approximately midnight UTC. For precise midnight resets, use a scheduled Worker to explicitly delete the key.
- **Queue batch size of 10** keeps individual consumer invocations short and reduces partial-failure blast radius.
- **Dead letter queue** captures messages that exhaust retries; monitor it via a separate alert Worker.
- **Bounce recording** requires webhook integration with MailChannels or your ESP; insert `UPDATE warmup_sends SET status='bounced', bounce_type='hard' WHERE email=?` from your webhook handler.
- The hard-bounce exclusion sub-query in the recipient SELECT prevents re-sending to known-bad addresses across future warm-up days.

## Anti-patterns

- Do not send to cold or unengaged lists during warm-up. ISP engagement signals heavily influence inbox placement; positive-engagement recipients improve your sender reputation fastest.
- Do not skip the bounce-rate check. Exceeding a 5% hard bounce rate risks immediate domain/IP blacklisting.
- Do not use `Math.random()` for daily cap distribution across recipient segments — deterministic ordering from D1 is more predictable.
- Do not rely on KV alone for bounce state; KV does not support atomic compare-and-swap across Workers, making D1 the right store for counts that must be durable.

## Gotchas

- KV `expirationTtl` is relative to the time of the `put` call, not to midnight. Counters may roll over at slightly different times each day. For strict calendar-day resets, delete the key at midnight via a cron.
- Queue consumers must call `msg.ack()` or `msg.retry()` explicitly; un-acked messages are automatically retried after the visibility timeout.
- Cloudflare Queues guarantee at-least-once delivery; the `warmup_sends` UNIQUE constraint will catch duplicates if you add one.
- MailChannels does not currently return bounce events synchronously; integrate with their webhook or use a dedicated inbound address for bounce replies.

## Verification

```bash
# Initialise KV with a start date (simulate day 3)
npx wrangler kv key put --binding=KV warmup:start_date "2026-08-22"

# Seed a recipient
npx wrangler d1 execute warmup-db \
  --command "INSERT INTO warmup_recipients (email) VALUES ('engaged@example.com')"

# Fire the cron manually
curl https://<worker>.workers.dev/__scheduled?cron=0+9+*+*+*

# Check enqueued messages in the Cloudflare dashboard
# Queue: warmup-send-queue → Messages

# Check D1 for send records
npx wrangler d1 execute warmup-db \
  --command "SELECT * FROM warmup_sends ORDER BY sent_at DESC LIMIT 10"
```

## Related

- `documentation/docs/policies/email/workers-transactional-email-queue.md`
- `documentation/docs/policies/email/bounce-handling-queues.md`
- `documentation/docs/policies/email/workers-email-suppression-list-kv.md`
- `documentation/docs/policies/email/mailchannels-dkim-workers.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/d1/
- https://api.mailchannels.net/tx/v1/documentation
- https://sendgrid.com/docs/ui/sending-email/ip-warmup-schedule/ (schedule reference)
