# Transactional Email Queue with Cloudflare Queues for Reliability

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Sending transactional email synchronously inside a request handler couples the user-facing response latency to ESP API latency (typically 100–500 ms) and creates silent failures when the ESP is unavailable or rate-limiting. A welcome email that fails to send because SendGrid is having an incident causes irreversible user experience damage.

**Cloudflare Queues** provides a durable, at-least-once delivery buffer between the request that *triggers* the email and the Worker that *sends* it. Failures retry automatically with configurable backoff. The triggering request returns immediately.

---

## Context

Cloudflare Queues operates on a producer-consumer model:

- **Producer Worker** — receives the application event (user signed up, order placed) and enqueues a message.
- **Consumer Worker** — processes messages from the queue, calls the ESP API, records the result in D1, and either completes (ack) or retries (nack).

Messages are buffered durably by Cloudflare; the consumer is invoked with a batch when messages are available or when the `max_batch_timeout` is reached, whichever comes first.

Key guarantees:
- **At-least-once delivery** — messages are never dropped; they may be delivered more than once on retry.
- **Retry with dead-letter queue** — after `max_retries` attempts, messages are routed to a dead-letter queue (DLQ) for inspection.
- **No external broker** — fully managed, no Kafka/SQS configuration required.

---

## Section 1: Wrangler Configuration

```toml
# wrangler.toml
name = "email-queue-system"
main = "src/index.ts"
compatibility_date = "2026-01-01"

# ---- Queues ----
[[queues.producers]]
binding  = "EMAIL_QUEUE"
queue    = "transactional-email"

[[queues.consumers]]
queue             = "transactional-email"
max_batch_size    = 10        # messages per consumer invocation
max_batch_timeout = 5         # seconds to wait before flushing a partial batch
max_retries       = 5         # attempts before DLQ
dead_letter_queue = "transactional-email-dlq"
retry_delay       = 30        # seconds between retries (exponential backoff multiplied by Queues)

[[queues.consumers]]
queue             = "transactional-email-dlq"
max_batch_size    = 5
max_batch_timeout = 30

# ---- D1 for send log ----
[[d1_databases]]
binding       = "DB"
database_name = "email-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
RESEND_API_KEY = ""   # set via: wrangler secret put RESEND_API_KEY
```

---

## Section 2: D1 Send Log Schema

```sql
-- migrations/0001_email_send_log.sql
CREATE TABLE IF NOT EXISTS email_send_log (
  id              TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  idempotency_key TEXT    UNIQUE NOT NULL,
  to_address      TEXT    NOT NULL,
  template        TEXT    NOT NULL,
  subject         TEXT,
  status          TEXT    NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','sent','failed','dlq')),
  esp_message_id  TEXT,
  attempts        INTEGER NOT NULL DEFAULT 0,
  queued_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  sent_at         TEXT,
  error_message   TEXT,
  payload         TEXT    -- original JSON payload for audit / resend
);

CREATE INDEX IF NOT EXISTS idx_send_log_status ON email_send_log (status);
CREATE INDEX IF NOT EXISTS idx_send_log_to     ON email_send_log (to_address);
```

```bash
wrangler d1 execute email-db --file=migrations/0001_email_send_log.sql
```

---

## Section 3: Message Schema

Define a typed envelope for queue messages.

```typescript
// src/types.ts

export type EmailTemplate =
  | "welcome"
  | "order-confirmation"
  | "password-reset"
  | "magic-link"
  | "invoice";

export interface EmailQueueMessage {
  /** Idempotency key — prevents duplicate sends on retry */
  idempotencyKey: string;
  to: string;
  template: EmailTemplate;
  subject: string;
  /** Template variables */
  data: Record<string, unknown>;
  /** ISO-8601 timestamp when the event occurred */
  triggeredAt: string;
}
```

---

## Section 4: Producer — Enqueue an Email

The producer Worker receives application events (HTTP POST, Durable Object state change, etc.) and enqueues the email message. The request returns to the caller in < 5 ms.

```typescript
// src/producer.ts
import type { Queue } from "@cloudflare/workers-types";
import type { EmailQueueMessage, EmailTemplate } from "./types";

export interface ProducerEnv {
  EMAIL_QUEUE: Queue<EmailQueueMessage>;
  DB: D1Database;
}

function generateIdempotencyKey(to: string, template: string, triggeredAt: string): string {
  // Stable key: same email + template + event time = same key
  return `${template}:${to.toLowerCase()}:${triggeredAt}`;
}

export async function enqueueEmail(
  to: string,
  template: EmailTemplate,
  subject: string,
  data: Record<string, unknown>,
  env: ProducerEnv
): Promise<string> {
  const triggeredAt = new Date().toISOString();
  const idempotencyKey = generateIdempotencyKey(to, template, triggeredAt);

  // Pre-insert the send log row to enable idempotency checks in the consumer
  await env.DB.prepare(`
    INSERT INTO email_send_log (idempotency_key, to_address, template, subject, payload)
    VALUES (?1, LOWER(?2), ?3, ?4, ?5)
    ON CONFLICT (idempotency_key) DO NOTHING
  `)
    .bind(
      idempotencyKey,
      to,
      template,
      subject,
      JSON.stringify(data)
    )
    .run();

  const message: EmailQueueMessage = {
    idempotencyKey,
    to,
    template,
    subject,
    data,
    triggeredAt,
  };

  await env.EMAIL_QUEUE.send(message, {
    contentType: "json",
    // Delay delivery by 2 s to allow the DB row to become consistent
    delaySeconds: 2,
  });

  return idempotencyKey;
}

// Example: call from your registration handler
export async function handleRegistration(
  request: Request,
  env: ProducerEnv
): Promise<Response> {
  const body = await request.json<{ email: string; name: string }>();

  const idempotencyKey = await enqueueEmail(
    body.email,
    "welcome",
    `Welcome to Orchords, ${body.name}!`,
    { name: body.name },
    env
  );

  return Response.json({ queued: true, idempotencyKey }, { status: 202 });
}
```

---

## Section 5: Consumer — Send via ESP

The consumer Worker processes batches from the queue, calls the ESP, and updates the D1 log. Each message is individually acked or nacked.

```typescript
// src/consumer.ts
import type { MessageBatch, Message, D1Database } from "@cloudflare/workers-types";
import type { EmailQueueMessage } from "./types";
import { renderTemplate } from "./templates";

export interface ConsumerEnv {
  DB: D1Database;
  RESEND_API_KEY: string;
}

async function sendViaResend(
  message: EmailQueueMessage,
  apiKey: string
): Promise<string> {
  const html = renderTemplate(message.template, message.data);

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: "noreply@example.com",
      to: [message.to],
      subject: message.subject,
      html,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Resend API ${response.status}: ${error}`);
  }

  const json = await response.json<{ id: string }>();
  return json.id;
}

async function updateSendLog(
  idempotencyKey: string,
  status: "sent" | "failed",
  db: D1Database,
  espMessageId?: string,
  errorMessage?: string
): Promise<void> {
  await db
    .prepare(`
      UPDATE email_send_log
      SET
        status         = ?2,
        esp_message_id = ?3,
        error_message  = ?4,
        sent_at        = CASE WHEN ?2 = 'sent' THEN strftime('%Y-%m-%dT%H:%M:%SZ','now') ELSE NULL END,
        attempts       = attempts + 1
      WHERE idempotency_key = ?1
    `)
    .bind(idempotencyKey, status, espMessageId ?? null, errorMessage ?? null)
    .run();
}

export async function handleEmailBatch(
  batch: MessageBatch<EmailQueueMessage>,
  env: ConsumerEnv
): Promise<void> {
  for (const msg of batch.messages) {
    const payload = msg.body;

    // Idempotency check: skip if already sent
    const existing = await env.DB.prepare(`
      SELECT status FROM email_send_log WHERE idempotency_key = ?1
    `)
      .bind(payload.idempotencyKey)
      .first<{ status: string }>();

    if (existing?.status === "sent") {
      msg.ack(); // already delivered — ack to remove from queue
      continue;
    }

    try {
      const espId = await sendViaResend(payload, env.RESEND_API_KEY);
      await updateSendLog(payload.idempotencyKey, "sent", env.DB, espId);
      msg.ack();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      console.error(`Failed to send ${payload.idempotencyKey}: ${errorMessage}`);
      await updateSendLog(payload.idempotencyKey, "failed", env.DB, undefined, errorMessage);
      msg.retry({ delaySeconds: 30 }); // back-pressure into queue
    }
  }
}
```

---

## Section 6: Dead-Letter Queue Consumer

Messages that exhaust all retries land in the DLQ. The DLQ consumer marks them in D1 and optionally alerts.

```typescript
// src/dlq-consumer.ts
import type { MessageBatch, D1Database } from "@cloudflare/workers-types";
import type { EmailQueueMessage } from "./types";

export interface DlqEnv {
  DB: D1Database;
  ALERT_WEBHOOK_URL: string;
}

export async function handleDlqBatch(
  batch: MessageBatch<EmailQueueMessage>,
  env: DlqEnv
): Promise<void> {
  for (const msg of batch.messages) {
    const payload = msg.body;

    await env.DB.prepare(`
      UPDATE email_send_log
      SET status = 'dlq', attempts = attempts + 1
      WHERE idempotency_key = ?1
    `)
      .bind(payload.idempotencyKey)
      .run();

    // Alert on-call channel
    if (env.ALERT_WEBHOOK_URL) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `Email DLQ: ${payload.template} to ${payload.to} failed all retries (key: ${payload.idempotencyKey})`,
        }),
      });
    }

    msg.ack(); // Ack so DLQ doesn't re-deliver infinitely
  }
}
```

Main entrypoint wiring all handlers:

```typescript
// src/index.ts
import type { MessageBatch, ExecutionContext } from "@cloudflare/workers-types";
import { handleRegistration, type ProducerEnv } from "./producer";
import { handleEmailBatch, type ConsumerEnv } from "./consumer";
import { handleDlqBatch, type DlqEnv } from "./dlq-consumer";
import type { EmailQueueMessage } from "./types";

export type Env = ProducerEnv & ConsumerEnv & DlqEnv;

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/api/register" && request.method === "POST") {
      return handleRegistration(request, env);
    }
    return new Response("Not Found", { status: 404 });
  },

  async queue(batch: MessageBatch<EmailQueueMessage>, env: Env): Promise<void> {
    if (batch.queue === "transactional-email-dlq") {
      return handleDlqBatch(batch, env);
    }
    return handleEmailBatch(batch, env);
  },
};
```

---

## Anti-Patterns

- **Sending directly inside `fetch`** — ties user response time to ESP latency and loses the retry safety net. Always enqueue and return 202.
- **Not writing an idempotency key before enqueuing** — at-least-once delivery means the consumer may run twice. Without a pre-written record and a `SELECT` guard, the same email sends twice.
- **Calling `msg.ack()` before confirming the ESP accepted the message** — if the Worker crashes between the ESP call and the ack, the message is lost. Ack only after a confirmed 2xx.
- **Ignoring DLQ messages** — a silent DLQ means users never receive transactional emails. Always monitor DLQ depth and alert.
- **Unbounded batch size** — setting `max_batch_size = 100` on a consumer that calls the ESP serially creates a 10-second batch processing window. Keep batches small enough that the consumer finishes well within the 30-second Worker CPU limit.

---

## Gotchas

- **Queue consumer timeout** — a single consumer invocation has a 30-second wall-clock limit. Process messages concurrently with `Promise.allSettled` for throughput, but cap concurrency to avoid rate-limit errors from the ESP.
- **`retry_delay` vs. `delaySeconds`** — `retry_delay` in `wrangler.toml` is the base delay applied by Queues on automatic retry. `msg.retry({ delaySeconds })` overrides this for a specific nack. Both are honored but the longer of the two wins.
- **Secrets in queue messages** — queue messages are stored in plain text by Cloudflare. Never put API keys, passwords, or PII beyond the recipient email in the message body. Use D1 to store sensitive data and reference it by ID.
- **Cold-start latency** — the consumer Worker may cold-start when the queue is idle. The first batch after a cold start will have higher latency. This is acceptable for email; if strict SLA is needed, use a Cron Trigger to keep the Worker warm.
- **Ordering** — Cloudflare Queues does not guarantee FIFO order within a batch. If order matters (e.g., a step-by-step onboarding sequence), encode sequence numbers in messages and handle reordering in the consumer.

---

## Verification

```bash
# Create queue via Wrangler
wrangler queues create transactional-email
wrangler queues create transactional-email-dlq

# Publish producer Worker
wrangler deploy

# Trigger a test email
curl -X POST https://email-queue-system.example.workers.dev/api/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","name":"Alice"}'
# Expected: {"queued":true,"idempotencyKey":"welcome:test@example.com:..."}

# Check D1 send log
wrangler d1 execute email-db \
  --command="SELECT idempotency_key, status, attempts, sent_at FROM email_send_log ORDER BY queued_at DESC LIMIT 10;"

# Monitor queue depth
wrangler queues list
# Check metrics in the Cloudflare dashboard: Workers → Queues → transactional-email
```

---

## Related

- `email-queue-architecture.md` — general queue design patterns
- `email-retry-exponential-backoff.md` — retry strategies
- `email-webhook-idempotency-deduplication.md` — idempotency in event pipelines
- `bounce-suppression-d1.md` — suppression list management with D1
- `transactional-email-rate-limiting-workers.md` — rate limiting outbound sends

---

## Sources

- [Cloudflare Queues documentation](https://developers.cloudflare.com/queues/)
- [Cloudflare Queues — Dead Letter Queues](https://developers.cloudflare.com/queues/configuration/dead-letter-queues/)
- [Cloudflare Queues — Consumer batching](https://developers.cloudflare.com/queues/configuration/consumer-concurrency/)
- [Resend API reference](https://resend.com/docs/api-reference/emails/send-email)
- [RFC 5321 §4.2 — SMTP reply codes](https://datatracker.ietf.org/doc/html/rfc5321#section-4.2)
