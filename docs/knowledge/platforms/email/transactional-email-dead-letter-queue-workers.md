# Transactional Email Dead-Letter Queue on Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Transactional emails (password resets, order confirmations, invoices) must be delivered
exactly once. When a downstream ESP rejects a send with a 5xx error or the Worker itself
throws, Cloudflare Queues retries the message up to its configured maximum — but after
exhausting retries the message is silently dropped by default. A dead-letter queue (DLQ)
captures those permanently-failed messages so they can be inspected, replayed, or
escalated without data loss.

## Context

Cloudflare Queues supports a `deadLetterQueue` binding on a queue consumer. Messages that
exceed the `maxRetries` threshold are automatically routed to the named DLQ instead of
being discarded. A separate lightweight consumer reads from the DLQ, writes each failure
to D1 with full context, and optionally pages the on-call team via an outbound webhook.
The primary send queue uses exponential backoff via `retryDelay` on `message.retry()`.

## Primary Send Queue Producer

```typescript
export interface Env {
  SEND_QUEUE: Queue<TransactionalJob>;
}

interface TransactionalJob {
  to: string;
  subject: string;
  html: string;
  idempotencyKey: string;
  attemptCount?: number;
  enqueuedAt: string;
}

// Called from an API Worker (order service, auth service, etc.)
export async function enqueueTransactionalEmail(
  env: Env,
  job: Omit<TransactionalJob, "enqueuedAt">
): Promise<void> {
  await env.SEND_QUEUE.send(
    { ...job, enqueuedAt: new Date().toISOString() },
    { contentType: "json" }
  );
}
```

## Send Consumer with Retry and DLQ Routing

```typescript
import { EmailMessage } from "cloudflare:email";
import { createMimeMessage } from "mimetext";

export interface Env {
  SEND_QUEUE: Queue<TransactionalJob>;
  DLQ: Queue<FailedJob>;
  DB: D1Database;
  EMAIL_SENDER: SendEmail;
}

interface FailedJob {
  original: TransactionalJob;
  lastError: string;
  failedAt: string;
}

// wrangler.toml:
// [[queues.consumers]]
// queue = "transactional-send"
// max_retries = 5
// dead_letter_queue = "transactional-dlq"
// retry_delay = 30          # seconds; exponential backoff applied by the runtime

export default {
  async queue(
    batch: MessageBatch<TransactionalJob>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;

      // Idempotency guard — skip if already sent successfully.
      const existing = await env.DB.prepare(
        `SELECT id FROM sent_emails WHERE idempotency_key = ? AND status = 'sent'`
      )
        .bind(job.idempotencyKey)
        .first<{ id: number }>();

      if (existing) {
        msg.ack(); // Already delivered; do not retry.
        continue;
      }

      try {
        const msg_ = createMimeMessage();
        msg_.setSender({ name: "ACME", addr: "no-reply@mail.acme.example" });
        msg_.setRecipient(job.to);
        msg_.setSubject(job.subject);
        msg_.addMessage({ contentType: "text/html", data: job.html });

        const emailMsg = new EmailMessage(
          "no-reply@mail.acme.example",
          job.to,
          msg_.asRaw()
        );
        await env.EMAIL_SENDER.send(emailMsg);

        await env.DB.prepare(
          `INSERT OR REPLACE INTO sent_emails
             (idempotency_key, recipient, subject, status, sent_at)
           VALUES (?, ?, ?, 'sent', ?)`
        )
          .bind(job.idempotencyKey, job.to, job.subject, new Date().toISOString())
          .run();

        msg.ack();
      } catch (err) {
        const delay = Math.min(
          30 * 2 ** (job.attemptCount ?? 0),
          3600
        );
        // Increment attempt count in the body for next retry.
        msg.retry({
          delaySeconds: delay,
        });
      }
    }
  },
};
```

## DLQ Consumer — Persist and Alert

```typescript
export interface Env {
  DB: D1Database;
  ALERT_WEBHOOK: string; // secret binding -> Slack / PagerDuty URL
}

export default {
  async queue(
    batch: MessageBatch<FailedJob>,
    env: Env
  ): Promise<void> {
    const stmt = env.DB.prepare(
      `INSERT INTO dlq_emails
         (idempotency_key, recipient, subject, last_error, failed_at, original_enqueued_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    );

    const inserts = batch.messages.map((msg) => {
      const { original, lastError, failedAt } = msg.body;
      return stmt.bind(
        original.idempotencyKey,
        original.to,
        original.subject,
        lastError,
        failedAt,
        original.enqueuedAt
      );
    });

    await env.DB.batch(inserts);

    // Fire-and-forget alert.
    const payload = {
      text: `*DLQ Alert* — ${batch.messages.length} transactional email(s) permanently failed. Check \`dlq_emails\` table.`,
    };
    await fetch(env.ALERT_WEBHOOK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => undefined); // Never let alert failure block ack.

    batch.ackAll();
  },
};
```

## D1 Schema

```sql
-- migrations/0001_transactional_queues.sql
CREATE TABLE IF NOT EXISTS sent_emails (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key  TEXT NOT NULL UNIQUE,
  recipient        TEXT NOT NULL,
  subject          TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'sent',
  sent_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dlq_emails (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key        TEXT NOT NULL,
  recipient              TEXT NOT NULL,
  subject                TEXT NOT NULL,
  last_error             TEXT,
  failed_at              TEXT NOT NULL,
  original_enqueued_at   TEXT NOT NULL,
  replayed_at            TEXT
);
CREATE INDEX idx_dlq_recipient ON dlq_emails(recipient);
```

## Anti-patterns

- Using `batch.ackAll()` unconditionally in the send consumer — failed messages silently
  disappear instead of being retried or routed to the DLQ.
- Setting `maxRetries` to 0 — messages go directly to the DLQ on any error, bypassing
  all retry logic and causing alert fatigue.
- Not implementing an idempotency guard — after a transient ESP 5xx, the Worker may retry
  successfully, and without a guard the email is sent twice.

## Gotchas

- The `deadLetterQueue` binding must be declared in `wrangler.toml` under
  `[[queues.consumers]]`; it cannot be set via the dashboard alone for Workers deployed
  with Wrangler.
- Cloudflare Queues does not currently support automatic exponential backoff — the
  `delaySeconds` value in `msg.retry()` must be computed by the application.
- DLQ messages carry the same body type as the source queue; they are not wrapped in an
  envelope, so the DLQ consumer must handle the `TransactionalJob` shape directly or be
  wrapped in a `FailedJob` at the point of `msg.retry()` (not possible). Enrich the
  body before enqueuing, not in the DLQ consumer.

## Verification

```bash
# Trigger a deliberate failure by sending to a non-existent address.
curl -X POST https://api.acme.example/send-test \
  -H "Content-Type: application/json" \
  -d '{"to":"nonexistent@invalid.example","subject":"DLQ test","idempotencyKey":"dlq-test-001"}'

# After max_retries are exhausted, check the DLQ table.
wrangler d1 execute EMAIL_DB \
  --command "SELECT idempotency_key, recipient, last_error, failed_at FROM dlq_emails ORDER BY failed_at DESC LIMIT 5;" \
  --remote
```

## Related

- `email/transactional-queue-cloudflare-queues.md`
- `email/email-retry-exponential-backoff.md`
- `email/transactional-email-rate-limiting-workers.md`

## Sources

- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://developers.cloudflare.com/email-routing/email-workers/send-email-workers/
