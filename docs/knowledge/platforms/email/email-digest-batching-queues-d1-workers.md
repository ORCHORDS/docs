# Email Digest Batching with Cloudflare Queues and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to send a daily or hourly digest email instead of flooding users with individual notifications. Individual events arrive continuously but the end-user should receive one combined HTML email per time window.

## Context

Cloudflare Queues acts as a buffer for incoming notification events. A D1 table (`digest_items`) stores each event row. A Cron Trigger fires on schedule, queries D1 for undelivered rows grouped by user, renders a digest, sends via MailChannels, and marks rows `sent`. If the send fails, rows remain `undelivered` and are picked up on the next run.

Requirements:
- Cloudflare Workers (Queue producer + Queue consumer + Cron handler)
- D1 database bound as `DB`
- Queue bound as `DIGEST_QUEUE`
- MailChannels send permission (Workers send email)

## Queue Consumer and D1 Schema

```typescript
// schema.sql — run once via `wrangler d1 execute DB --file schema.sql`
// CREATE TABLE digest_items (
//   id          INTEGER PRIMARY KEY AUTOINCREMENT,
//   user_id     TEXT NOT NULL,
//   recipient   TEXT NOT NULL,
//   subject     TEXT NOT NULL,
//   body        TEXT NOT NULL,
//   queued_at   TEXT NOT NULL DEFAULT (datetime('now')),
//   status      TEXT NOT NULL DEFAULT 'undelivered'
// );
// CREATE INDEX idx_digest_user_status ON digest_items(user_id, status);

import PostalMime from 'postal-mime';

export interface Env {
  DB: D1Database;
  DIGEST_QUEUE: Queue;
}

interface NotificationPayload {
  user_id: string;
  recipient: string;
  subject: string;
  body: string;
}

// Queue consumer: persist each event to D1
export default {
  async queue(batch: MessageBatch<NotificationPayload>, env: Env): Promise<void> {
    const stmt = env.DB.prepare(
      `INSERT INTO digest_items (user_id, recipient, subject, body)
       VALUES (?, ?, ?, ?)`
    );
    const inserts = batch.messages.map((msg) =>
      stmt.bind(
        msg.body.user_id,
        msg.body.recipient,
        msg.body.subject,
        msg.body.body
      )
    );
    await env.DB.batch(inserts);
    batch.ackAll();
  },

  // Cron Trigger: send digests on schedule (e.g. "0 8 * * *" for 08:00 UTC daily)
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(sendDigests(env));
  },
};

async function sendDigests(env: Env): Promise<void> {
  // Fetch distinct users that have undelivered items
  const users = await env.DB.prepare(
    `SELECT DISTINCT user_id, recipient FROM digest_items WHERE status = 'undelivered'`
  ).all<{ user_id: string; recipient: string }>();

  for (const { user_id, recipient } of users.results) {
    const rows = await env.DB.prepare(
      `SELECT id, subject, body, queued_at FROM digest_items
       WHERE user_id = ? AND status = 'undelivered'
       ORDER BY queued_at ASC`
    ).all<{ id: number; subject: string; body: string; queued_at: string }>({ user_id });

    const items = rows.results;
    if (items.length === 0) continue;

    const html = renderDigest(recipient, items);

    const sent = await sendViaMailChannels(recipient, `Your digest (${items.length} updates)`, html);

    if (sent) {
      const ids = items.map((r) => r.id);
      await env.DB.prepare(
        `UPDATE digest_items SET status = 'sent' WHERE id IN (${ids.map(() => '?').join(',')})`
      ).bind(...ids).run();
    }
    // On failure: rows keep status='undelivered' and are retried next Cron run
  }
}

function renderDigest(recipient: string, items: { subject: string; body: string; queued_at: string }[]): string {
  const entries = items
    .map((i) => `<li><strong>${i.subject}</strong><br/>${i.body}<br/><small>${i.queued_at}</small></li>`)
    .join('');
  return `<html><body><h2>Your Digest</h2><p>Hi ${recipient},</p><ul>${entries}</ul></body></html>`;
}

async function sendViaMailChannels(to: string, subject: string, html: string): Promise<boolean> {
  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: 'digest@yourdomain.com', name: 'Digest Service' },
      subject,
      content: [{ type: 'text/html', value: html }],
    }),
  });
  return res.status === 202;
}
```

## wrangler.toml Configuration

```toml
name = "digest-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "digest-db"
database_id = "<your-d1-id>"

[[queues.producers]]
binding = "DIGEST_QUEUE"
queue = "digest-queue"

[[queues.consumers]]
queue = "digest-queue"
max_batch_size = 100
max_batch_timeout = 30

[triggers]
crons = ["0 8 * * *"]
```

## Producing Events from Another Worker

Any upstream Worker publishes to the queue:

```typescript
await env.DIGEST_QUEUE.send({
  user_id: 'usr_123',
  recipient: 'user@example.com',
  subject: 'New comment on your post',
  body: 'Alice replied: "Great article!"',
} satisfies NotificationPayload);
```

## Anti-patterns

- Do not send email directly inside the Queue consumer — high-volume events would exhaust MailChannels rate limits.
- Do not delete rows after processing; keeping `sent` rows gives an audit trail. Prune old rows on a separate Cron.
- Do not use `SELECT *` without an index on `(user_id, status)`; add the index shown in the schema.

## Gotchas

- Cron Triggers have a minimum resolution of 1 minute; sub-minute digests require a different architecture.
- D1 `batch()` is limited to 100 statements per call; chunk large batches accordingly.
- MailChannels returns 202 on acceptance, not guaranteed delivery. Track bounces separately.
- If the Cron handler exceeds the 30-second CPU limit, split large user sets across multiple Cron patterns.

## Verification

```bash
# Publish a test notification event
wrangler queues publish digest-queue '{"user_id":"usr_test","recipient":"test@example.com","subject":"Test","body":"Hello"}'

# Query D1 to confirm row inserted
wrangler d1 execute digest-db --command "SELECT * FROM digest_items WHERE status='undelivered' LIMIT 5;"

# Trigger the Cron manually via a test route or wrangler tail to observe execution
wrangler tail digest-worker --format pretty
```

## Related

- `email-smtp-pipeline-workers-queues.md`
- `email-auto-responder-out-of-office-d1-workers.md`
- [Cloudflare Queues docs](https://developers.cloudflare.com/queues/)
- [Cloudflare D1 docs](https://developers.cloudflare.com/d1/)

## Sources

- https://developers.cloudflare.com/queues/get-started/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://api.mailchannels.net/tx/v1/documentation
