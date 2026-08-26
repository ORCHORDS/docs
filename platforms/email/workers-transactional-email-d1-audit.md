# Transactional Email Pipeline with D1 Audit Trail in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You send transactional emails (receipts, password resets, notifications) from Cloudflare Workers and need a durable audit trail showing delivery status, retry attempts, and stuck-job alerting. Without a persistent log, failed sends are invisible and retry logic is ad hoc.

---

## Context
Cloudflare Queues decouple email submission from delivery: a producer enqueues a job, and a consumer Worker calls MailChannels, writing status back to D1. The `email_jobs` table tracks every attempt with `status in {pending, sent, failed}` and an `attempts` counter. On failure, the consumer uses `message.retry({ delaySeconds })` with exponential back-off up to a configured maximum. A Cron Trigger scans for jobs stuck in `pending` for more than one hour and sends an alert email to the ops team.

---

## Section 1 — D1 Schema & Wrangler Config

```sql
-- migrations/0001_email_jobs.sql
CREATE TABLE IF NOT EXISTS email_jobs (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  to_email    TEXT NOT NULL,
  template    TEXT NOT NULL,
  payload     TEXT NOT NULL DEFAULT '{}',
  status      TEXT NOT NULL DEFAULT 'pending',
  attempts    INTEGER NOT NULL DEFAULT 0,
  error       TEXT,
  enqueued_at INTEGER NOT NULL DEFAULT (unixepoch()),
  sent_at     INTEGER,
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_email_jobs_status     ON email_jobs(status);
CREATE INDEX IF NOT EXISTS idx_email_jobs_enqueued   ON email_jobs(enqueued_at);
```

```toml
# wrangler.toml
name = "email-pipeline"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[queues.producers]]
binding   = "EMAIL_QUEUE"
queue     = "email-jobs"

[[queues.consumers]]
queue            = "email-jobs"
max_batch_size   = 10
max_batch_timeout = 30
max_retries      = 3
dead_letter_queue = "email-jobs-dlq"

[[d1_databases]]
binding       = "DB"
database_name = "email-pipeline-db"
database_id   = "<your-d1-database-id>"

[vars]
FROM_EMAIL   = "noreply@example.com"
OPS_EMAIL    = "ops@example.com"
MAX_ATTEMPTS = "5"

[triggers]
crons = ["0 * * * *"]
```

---

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  EMAIL_QUEUE: Queue<EmailJobMessage>;
  FROM_EMAIL: string;
  OPS_EMAIL: string;
  MAX_ATTEMPTS: string;
}

interface EmailJobMessage {
  jobId: string;
  to: string;
  template: string;
  payload: Record<string, unknown>;
}

function renderTemplate(
  template: string,
  payload: Record<string, unknown>
): { subject: string; html: string } {
  const templates: Record<string, (p: Record<string, unknown>) => { subject: string; html: string }> = {
    welcome: (p) => ({
      subject: `Welcome, ${p.name}!`,
      html: `<h1>Welcome to Orchords</h1><p>Hi ${p.name}, thanks for joining.</p>`,
    }),
    password_reset: (p) => ({
      subject: 'Reset your password',
      html: `<p>Click <a >here</a> to reset your password. Expires in 1 hour.</p>`,
    }),
    receipt: (p) => ({
      subject: `Your order #${p.orderId}`,
      html: `<p>Thank you for your order #${p.orderId}. Total: $${p.total}</p>`,
    }),
  };
  const fn = templates[template];
  if (!fn) throw new Error(`Unknown template: ${template}`);
  return fn(payload);
}

async function sendViaMailChannels(
  from: string,
  to: string,
  subject: string,
  html: string
): Promise<void> {
  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: from },
      subject,
      content: [{ type: 'text/html', value: html }],
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`MailChannels ${res.status}: ${text}`);
  }
}

async function processEmailJob(
  env: Env,
  message: Message<EmailJobMessage>
): Promise<void> {
  const { jobId, to, template, payload } = message.body;
  const maxAttempts = parseInt(env.MAX_ATTEMPTS, 10);

  await env.DB
    .prepare(`UPDATE email_jobs SET attempts = attempts + 1, updated_at = unixepoch() WHERE id = ?`)
    .bind(jobId)
    .run();

  const row = await env.DB
    .prepare(`SELECT attempts FROM email_jobs WHERE id = ?`)
    .bind(jobId)
    .first<{ attempts: number }>();

  const attempts = row?.attempts ?? 1;

  try {
    const { subject, html } = renderTemplate(template, payload);
    await sendViaMailChannels(env.FROM_EMAIL, to, subject, html);

    await env.DB
      .prepare(
        `UPDATE email_jobs
         SET status = 'sent', sent_at = unixepoch(), updated_at = unixepoch(), error = NULL
         WHERE id = ?`
      )
      .bind(jobId)
      .run();

    message.ack();
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);

    if (attempts >= maxAttempts) {
      await env.DB
        .prepare(
          `UPDATE email_jobs
           SET status = 'failed', updated_at = unixepoch(), error = ?
           WHERE id = ?`
        )
        .bind(errorMsg, jobId)
        .run();
      message.ack();
    } else {
      await env.DB
        .prepare(`UPDATE email_jobs SET error = ?, updated_at = unixepoch() WHERE id = ?`)
        .bind(errorMsg, jobId)
        .run();
      const delaySeconds = Math.pow(2, attempts) * 30;
      message.retry({ delaySeconds });
    }
  }
}

async function alertStuckJobs(env: Env): Promise<void> {
  const oneHourAgo = Math.floor(Date.now() / 1000) - 3600;
  const { results } = await env.DB
    .prepare(
      `SELECT id, to_email, template, attempts, enqueued_at
       FROM email_jobs
       WHERE status = 'pending' AND enqueued_at < ?
       ORDER BY enqueued_at ASC
       LIMIT 50`
    )
    .bind(oneHourAgo)
    .all<{ id: string; to_email: string; template: string; attempts: number; enqueued_at: number }>();

  if (results.length === 0) return;

  const rows = results
    .map((r) => `<tr><td>${r.id}</td><td>${r.to_email}</td><td>${r.template}</td><td>${r.attempts}</td></tr>`)
    .join('');

  const html = `
    <h2>${results.length} email job(s) stuck in pending > 1 hour</h2>
    <table border="1">
      <tr><th>ID</th><th>To</th><th>Template</th><th>Attempts</th></tr>
      ${rows}
    </table>`;

  await sendViaMailChannels(
    env.FROM_EMAIL,
    env.OPS_EMAIL,
    `[ALERT] ${results.length} stuck email jobs`,
    html
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    const { to, template, payload = {} } = await request.json<Omit<EmailJobMessage, 'jobId'>>();
    const jobId = crypto.randomUUID();
    await env.DB
      .prepare(`INSERT INTO email_jobs (id, to_email, template, payload) VALUES (?, ?, ?, ?)`)
      .bind(jobId, to, template, JSON.stringify(payload))
      .run();
    await env.EMAIL_QUEUE.send({ jobId, to, template, payload });
    return Response.json({ ok: true, jobId }, { status: 202 });
  },

  async queue(batch: MessageBatch<EmailJobMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      await processEmailJob(env, message);
    }
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await alertStuckJobs(env);
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Integration Testing

```bash
# Apply schema
npx wrangler d1 execute email-pipeline-db --file=migrations/0001_email_jobs.sql

# Enqueue a welcome email
curl -X POST https://email-pipeline.example.com \
  -H 'Content-Type: application/json' \
  -d '{"to":"user@example.com","template":"welcome","payload":{"name":"Alice"}}'

# Poll job status
npx wrangler d1 execute email-pipeline-db \
  --command "SELECT id, status, attempts, error FROM email_jobs ORDER BY enqueued_at DESC LIMIT 5"

# Simulate stuck jobs alert
npx wrangler d1 execute email-pipeline-db \
  --command "UPDATE email_jobs SET enqueued_at = unixepoch() - 7200 WHERE status = 'pending'"
```

---

## Anti-patterns
- **Calling MailChannels synchronously in the fetch handler** — A slow or unavailable upstream blocks the response; always enqueue and return 202.
- **Retrying forever** — Without a `maxAttempts` ceiling, a persistently failing job fills the queue; gate retries and mark `failed` explicitly.
- **Storing payload in the queue message only** — Queue messages are not durable logs; always write the job to D1 before enqueuing so you have a record even if the queue drops it.
- **Using queue `maxRetries` as the only retry gate** — The queue-level retry count resets on Worker redeploy; track `attempts` in D1 for reliable backoff.

---

## Gotchas
- `message.retry({ delaySeconds })` only works inside a queue consumer; calling it in a fetch handler throws.
- D1 `INSERT` inside a queue consumer must complete before `message.ack()` / `message.retry()` to avoid a status update being skipped on consumer crash.
- The `dead_letter_queue` in `wrangler.toml` only captures messages that exhaust queue-level retries, not application-level failures you `ack()` after marking `failed`.
- Cron Trigger frequency is limited to once per minute minimum; for sub-minute monitoring, use a Durable Object alarm instead.

---

## Verification

```bash
# Confirm sent count
npx wrangler d1 execute email-pipeline-db \
  --command "SELECT status, COUNT(*) as n FROM email_jobs GROUP BY status"

# View failed jobs with errors
npx wrangler d1 execute email-pipeline-db \
  --command "SELECT id, to_email, error, attempts FROM email_jobs WHERE status = 'failed'"

# Tail consumer logs
npx wrangler tail email-pipeline
```

---

## Related
- `workers-email-list-management-d1.md`
- `workers-email-open-tracking-pixel.md`

---

## Sources
- Cloudflare Queues Docs — https://developers.cloudflare.com/queues/
- Cloudflare D1 Docs — https://developers.cloudflare.com/d1/
- MailChannels API Reference — https://api.mailchannels.net/tx/v1/documentation
