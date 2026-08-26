# Resend Batch Broadcast with Cloudflare Workers and Queues

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to send a broadcast (newsletter or product announcement) to tens of thousands of recipients
through Resend without hammering the API synchronously, losing progress on a crash, or exhausting the
Resend batch limit in a single Worker invocation.

## Context

Resend's `/emails/batch` endpoint accepts up to 100 messages per call and enforces per-account
rate limits. Cloudflare Workers have a 30-second CPU limit and Queues handle at-least-once delivery
with built-in retry and dead-letter semantics. The pattern: a scheduled trigger fans out batches of
recipient IDs onto a Queue; a Queue consumer pulls batches, builds payloads, calls Resend, and
records delivery status in D1.

Resend API base URL: `https://api.resend.com`
Relevant limit: 100 emails per batch call, 10 batch calls/sec on Pro plan.

---

## 1. D1 Schema

```sql
CREATE TABLE broadcasts (
  id         TEXT PRIMARY KEY,
  subject    TEXT NOT NULL,
  html_body  TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'queued', -- queued | sending | done | failed
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE broadcast_recipients (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  broadcast_id TEXT NOT NULL REFERENCES broadcasts(id),
  email        TEXT NOT NULL,
  name         TEXT,
  status       TEXT NOT NULL DEFAULT 'pending', -- pending | sent | failed
  resend_id    TEXT,
  sent_at      TEXT
);

CREATE INDEX idx_br_broadcast_pending
  ON broadcast_recipients(broadcast_id, status);
```

---

## 2. Scheduled Trigger — Fan-out Worker

```typescript
// src/fanout.ts
import type { Env } from './types';

export interface BroadcastQueueMessage {
  broadcastId: string;
  recipientIds: number[];
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    // Find broadcasts in 'queued' state
    const { results } = await env.DB.prepare(
      `SELECT id FROM broadcasts WHERE status = 'queued' LIMIT 5`
    ).all<{ id: string }>();

    for (const broadcast of results) {
      await fanOutBroadcast(broadcast.id, env);
    }
  },
};

async function fanOutBroadcast(broadcastId: string, env: Env): Promise<void> {
  // Mark as sending
  await env.DB.prepare(
    `UPDATE broadcasts SET status = 'sending' WHERE id = ?`
  ).bind(broadcastId).run();

  const BATCH_SIZE = 100;
  let offset = 0;

  while (true) {
    const { results } = await env.DB.prepare(
      `SELECT id FROM broadcast_recipients
       WHERE broadcast_id = ? AND status = 'pending'
       ORDER BY id LIMIT ? OFFSET ?`
    ).bind(broadcastId, BATCH_SIZE, offset).all<{ id: number }>();

    if (results.length === 0) break;

    const message: BroadcastQueueMessage = {
      broadcastId,
      recipientIds: results.map((r) => r.id),
    };

    await env.BROADCAST_QUEUE.send(message, { contentType: 'json' });
    offset += results.length;
    if (results.length < BATCH_SIZE) break;
  }
}
```

---

## 3. Queue Consumer — Send Worker

```typescript
// src/consumer.ts
import type { Env } from './types';
import type { BroadcastQueueMessage } from './fanout';

const RESEND_API = 'https://api.resend.com/emails/batch';

export default {
  async queue(
    batch: MessageBatch<BroadcastQueueMessage>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processBatch(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('Batch failed, retrying', err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function processBatch(
  payload: BroadcastQueueMessage,
  env: Env
): Promise<void> {
  const { broadcastId, recipientIds } = payload;

  // Fetch broadcast template
  const broadcast = await env.DB.prepare(
    `SELECT subject, html_body FROM broadcasts WHERE id = ?`
  ).bind(broadcastId).first<{ subject: string; html_body: string }>();

  if (!broadcast) throw new Error(`Broadcast ${broadcastId} not found`);

  // Fetch recipient rows
  const placeholders = recipientIds.map(() => '?').join(',');
  const { results: recipients } = await env.DB.prepare(
    `SELECT id, email, name FROM broadcast_recipients WHERE id IN (${placeholders})`
  ).bind(...recipientIds).all<{ id: number; email: string; name: string | null }>();

  // Build Resend batch payload
  const emails = recipients.map((r) => ({
    from: env.FROM_ADDRESS,
    to: r.email,
    subject: broadcast.subject,
    html: broadcast.html_body.replace('{{name}}', r.name ?? 'there'),
    headers: {
      'X-Broadcast-Id': broadcastId,
      'X-Recipient-Id': String(r.id),
    },
  }));

  const resp = await fetch(RESEND_API, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(emails),
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Resend batch error ${resp.status}: ${body}`);
  }

  const data = (await resp.json()) as Array<{ id: string; error?: string }>;

  // Record results back to D1
  const stmt = env.DB.prepare(
    `UPDATE broadcast_recipients
     SET status = ?, resend_id = ?, sent_at = datetime('now')
     WHERE id = ?`
  );

  const updates = data.map((result, idx) =>
    stmt.bind(
      result.error ? 'failed' : 'sent',
      result.id ?? null,
      recipients[idx].id
    )
  );

  await env.DB.batch(updates);
}
```

---

## 4. wrangler.toml Bindings

```toml
[[queues.producers]]
queue = "broadcast-queue"
binding = "BROADCAST_QUEUE"

[[queues.consumers]]
queue = "broadcast-queue"
max_batch_size = 10          # 10 queue msgs × 100 emails = 1000 emails/invocation
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "broadcast-dlq"

[[d1_databases]]
binding = "DB"
database_name = "email-db"
database_id = "<your-d1-id>"
```

---

## 5. Broadcast Completion Check (Cron)

```typescript
// Runs after fan-out cron to close out finished broadcasts
async function markCompletedBroadcasts(env: Env): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT DISTINCT broadcast_id FROM broadcast_recipients
     WHERE status = 'pending'`
  ).all<{ broadcast_id: string }>();

  const pendingIds = new Set(results.map((r) => r.broadcast_id));

  const { results: sending } = await env.DB.prepare(
    `SELECT id FROM broadcasts WHERE status = 'sending'`
  ).all<{ id: string }>();

  for (const b of sending) {
    if (!pendingIds.has(b.id)) {
      await env.DB.prepare(
        `UPDATE broadcasts SET status = 'done' WHERE id = ?`
      ).bind(b.id).run();
    }
  }
}
```

---

## Anti-patterns

- **Sending synchronously from a cron Worker**: CPU limit kills mid-send with no recovery point.
- **Batching more than 100 per Resend call**: API returns 400; the whole batch is lost.
- **Not recording `resend_id`**: You lose the ability to correlate webhook events to recipients.
- **Single retry without backoff**: Hammering Resend on rate-limit returns 429 in a tight loop.

## Gotchas

- Resend returns a 200 with per-email `error` objects inside the array; always inspect each element.
- Queue messages have a 128 KB payload limit; storing full HTML in the queue message will fail — keep only IDs and fetch content from D1.
- `max_batch_size` in the consumer controls how many queue messages are delivered per Worker invocation, not how many emails per Resend call.
- Dead-letter queue messages need their own consumer or periodic drain job; silent DLQ growth hides broadcast failures.

## Verification

```bash
# Check pending vs sent counts for a broadcast
wrangler d1 execute email-db --command \
  "SELECT status, COUNT(*) FROM broadcast_recipients WHERE broadcast_id='<id>' GROUP BY status"

# Tail consumer logs
wrangler tail --format pretty

# Inspect DLQ depth
wrangler queues list
```

## Related

- `resend-setup.md`
- `transactional-queue-cloudflare-queues.md`
- `email-drip-campaign-sequence-queues-workers.md`
- `email-digest-batching-queues-d1-workers.md`
- `email-retry-exponential-backoff.md`

## Sources

- https://resend.com/docs/api-reference/emails/send-batch-emails
- https://developers.cloudflare.com/queues/reference/how-queues-works/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/d1/
