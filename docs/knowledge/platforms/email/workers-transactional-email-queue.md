# Transactional Email Queue with Delivery Guarantees

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Emails sent inline inside a request handler fail silently when the upstream relay (MailChannels, SendGrid, Postmark) returns a 5xx or is temporarily unavailable. You need a durable queue so every email is attempted at least once, retried with back-off on failure, quarantined to a dead-letter queue after exhausting retries, and protected against duplicate sends when the same event is processed more than once.

---

## Context

Cloudflare Queues provide at-least-once delivery with a configurable retry policy and dead-letter queue. D1 stores a delivery ledger keyed on an idempotency key so duplicate producer messages result in exactly one send. A rate limiter using the Cloudflare Rate Limiting API (or a D1-backed token bucket) prevents burst sends from triggering relay-side throttling.

Prerequisites:
- Queue bound as `EMAIL_QUEUE` (producer) and consumed by the same or a separate Worker
- D1 database bound as `DB`
- MailChannels DKIM-enabled domain
- `wrangler.toml` with `[[queues.producers]]` and `[[queues.consumers]]` sections

---

## Solution

```typescript
// wrangler.toml (excerpt)
// [[queues.producers]]
// queue = "email-queue"
// binding = "EMAIL_QUEUE"
//
// [[queues.consumers]]
// queue = "email-queue"
// max_batch_size = 10
// max_batch_timeout = 5
// max_retries = 5
// dead_letter_queue = "email-dlq"

export interface Env {
  EMAIL_QUEUE: Queue<EmailMessage>;
  DB: D1Database;
  MAILCHANNELS_API_KEY: string; // via Workers secret
  MAX_SENDS_PER_MINUTE: string; // e.g. "60"
}

// ── D1 schema ─────────────────────────────────────────────────────────────────
// CREATE TABLE IF NOT EXISTS email_deliveries (
//   idempotency_key TEXT PRIMARY KEY,
//   to_address      TEXT NOT NULL,
//   subject         TEXT NOT NULL,
//   status          TEXT NOT NULL DEFAULT 'queued',  -- queued|sent|failed
//   attempts        INTEGER NOT NULL DEFAULT 0,
//   last_error      TEXT,
//   queued_at       TEXT NOT NULL,
//   sent_at         TEXT,
//   message_id      TEXT
// );
// CREATE TABLE IF NOT EXISTS rate_limit_buckets (
//   bucket_key  TEXT PRIMARY KEY,
//   tokens      REAL NOT NULL,
//   last_refill TEXT NOT NULL
// );

interface EmailMessage {
  idempotencyKey: string;
  to: string;
  from: string;
  subject: string;
  html: string;
  text?: string;
  replyTo?: string;
}

// ── Rate limiter (token-bucket via D1) ───────────────────────────────────────
async function acquireToken(db: D1Database, maxPerMinute: number): Promise<boolean> {
  const key = 'global-email';
  const now = Date.now();

  const { results } = await db
    .prepare('SELECT tokens, last_refill FROM rate_limit_buckets WHERE bucket_key = ?')
    .bind(key)
    .all<{ tokens: number; last_refill: string }>();

  let tokens: number;
  let lastRefill: number;

  if (!results.length) {
    tokens = maxPerMinute;
    lastRefill = now;
  } else {
    lastRefill = new Date(results[0].last_refill).getTime();
    const elapsedMinutes = (now - lastRefill) / 60_000;
    tokens = Math.min(maxPerMinute, results[0].tokens + elapsedMinutes * maxPerMinute);
  }

  if (tokens < 1) return false;

  await db
    .prepare(
      `INSERT INTO rate_limit_buckets (bucket_key, tokens, last_refill)
       VALUES (?, ?, ?)
       ON CONFLICT(bucket_key) DO UPDATE
         SET tokens = excluded.tokens - 1, last_refill = excluded.last_refill`
    )
    .bind(key, tokens - 1, new Date(now).toISOString())
    .run();

  return true;
}

// ── Idempotency guard ─────────────────────────────────────────────────────────
async function claimDelivery(
  db: D1Database,
  msg: EmailMessage
): Promise<'claimed' | 'duplicate' | 'already_sent'> {
  const { results } = await db
    .prepare('SELECT status FROM email_deliveries WHERE idempotency_key = ?')
    .bind(msg.idempotencyKey)
    .all<{ status: string }>();

  if (results.length) {
    return results[0].status === 'sent' ? 'already_sent' : 'duplicate';
  }

  await db
    .prepare(
      `INSERT INTO email_deliveries
         (idempotency_key, to_address, subject, status, attempts, queued_at)
       VALUES (?, ?, ?, 'queued', 0, ?)`
    )
    .bind(msg.idempotencyKey, msg.to, msg.subject, new Date().toISOString())
    .run();

  return 'claimed';
}

// ── MailChannels send ─────────────────────────────────────────────────────────
interface SendResult {
  messageId: string | null;
  ok: boolean;
  retryable: boolean;
  error?: string;
}

async function sendViaMailChannels(
  msg: EmailMessage,
  apiKey: string
): Promise<SendResult> {
  const payload = {
    personalizations: [{ to: [{ email: msg.to }] }],
    from: { email: msg.from },
    reply_to: msg.replyTo ? { email: msg.replyTo } : undefined,
    subject: msg.subject,
    content: [
      ...(msg.text ? [{ type: 'text/plain', value: msg.text }] : []),
      { type: 'text/html', value: msg.html },
    ],
  };

  let response: globalThis.Response;
  try {
    response = await fetch('https://api.mailchannels.net/tx/v1/send', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
      },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    // Network-level failure — always retryable
    return { messageId: null, ok: false, retryable: true, error: String(err) };
  }

  if (response.ok || response.status === 202) {
    const messageId = response.headers.get('x-message-id') ?? null;
    return { messageId, ok: true, retryable: false };
  }

  // 429 / 503 → retryable; 4xx (except 429) → permanent failure
  const retryable = response.status === 429 || response.status >= 500;
  const body = await response.text().catch(() => '');
  return {
    messageId: null,
    ok: false,
    retryable,
    error: `HTTP ${response.status}: ${body}`,
  };
}

// ── Exponential back-off delay hint ──────────────────────────────────────────
// Queues honour the retryDelay set in message.retry(). The consumer
// calculates the delay based on the delivery attempt count stored in D1.
function backoffSeconds(attempt: number): number {
  // 30s, 60s, 120s, 240s, 480s — capped at 8 minutes
  return Math.min(30 * 2 ** (attempt - 1), 480);
}

// ── Queue consumer ────────────────────────────────────────────────────────────
export default {
  async queue(
    batch: MessageBatch<EmailMessage>,
    env: Env
  ): Promise<void> {
    const maxPerMinute = parseInt(env.MAX_SENDS_PER_MINUTE, 10);

    for (const message of batch.messages) {
      const msg = message.body;

      // 1. Idempotency check
      const claim = await claimDelivery(env.DB, msg);
      if (claim === 'already_sent') {
        message.ack(); // already delivered — discard quietly
        continue;
      }

      // 2. Rate limit
      const tokenGranted = await acquireToken(env.DB, maxPerMinute);
      if (!tokenGranted) {
        // Requeue with a short delay; do NOT ack so Queues retries it
        message.retry({ delaySeconds: 5 });
        continue;
      }

      // 3. Increment attempt counter
      await env.DB
        .prepare(
          'UPDATE email_deliveries SET attempts = attempts + 1 WHERE idempotency_key = ?'
        )
        .bind(msg.idempotencyKey)
        .run();

      // 4. Send
      const { results: attemptRows } = await env.DB
        .prepare('SELECT attempts FROM email_deliveries WHERE idempotency_key = ?')
        .bind(msg.idempotencyKey)
        .all<{ attempts: number }>();
      const attempt = attemptRows[0]?.attempts ?? 1;

      const result = await sendViaMailChannels(msg, env.MAILCHANNELS_API_KEY);

      if (result.ok) {
        await env.DB
          .prepare(
            `UPDATE email_deliveries
             SET status = 'sent', sent_at = ?, message_id = ?
             WHERE idempotency_key = ?`
          )
          .bind(new Date().toISOString(), result.messageId, msg.idempotencyKey)
          .run();
        message.ack();
      } else if (!result.retryable) {
        // Permanent failure — write error, ack to stop retries (DLQ ingestion handled separately)
        await env.DB
          .prepare(
            `UPDATE email_deliveries
             SET status = 'failed', last_error = ?
             WHERE idempotency_key = ?`
          )
          .bind(result.error ?? 'unknown', msg.idempotencyKey)
          .run();
        message.ack();
      } else {
        // Retryable failure — persist error, let Queues retry with back-off
        await env.DB
          .prepare(
            'UPDATE email_deliveries SET last_error = ? WHERE idempotency_key = ?'
          )
          .bind(result.error ?? 'unknown', msg.idempotencyKey)
          .run();
        message.retry({ delaySeconds: backoffSeconds(attempt) });
      }
    }
  },

  // Producer-side helper — call from any Worker to enqueue an email
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });
    const msg = await request.json<EmailMessage>();
    if (!msg.idempotencyKey || !msg.to || !msg.subject || !msg.html) {
      return new Response('Missing required fields', { status: 400 });
    }
    await env.EMAIL_QUEUE.send(msg);
    return Response.json({ queued: true, idempotencyKey: msg.idempotencyKey }, { status: 202 });
  },
};
```

---

## Implementation Details

- **Queue consumer vs. inline send**: the producer Worker simply calls `env.EMAIL_QUEUE.send(msg)` and returns immediately. The consumer Worker processes the message asynchronously. This decouples request latency from SMTP relay latency.
- **Idempotency key design**: use a deterministic key derived from the triggering event, e.g. `sha256(userId + ':' + eventType + ':' + eventId)`. This ensures that if the event is replicated (e.g., a Webhook fires twice) the email is sent exactly once.
- **Dead letter queue**: after `max_retries` exhausted attempts, Queues automatically routes the message to the `dead_letter_queue` binding. Add a separate consumer for `email-dlq` that writes to a Slack webhook or sends an alert to the ops team.
- **Token bucket in D1**: a D1-backed token bucket is simple but adds a write per send. For high-volume senders, replace with a Durable Object that holds the bucket state in memory and persists it periodically.
- **Retry delay**: `message.retry({ delaySeconds })` is supported from Workers Runtime `2024-01-12` and requires the `queues` consumer binding to be on a Worker deployed after that date.

---

## Anti-patterns

- **Sending email in a `fetch` handler without a queue** — any relay timeout beyond the 30-second Worker CPU limit causes a silent failure.
- **Using wall-clock time as an idempotency key** — clocks skew across invocations; use a deterministic hash of the event instead.
- **ACKing on permanent failure without logging** — permanently failed messages are silently dropped. Always write the error to D1 or a log sink before ACKing.
- **Setting `max_retries` to a large number without exponential back-off** — hammers the relay during an outage and consumes rate-limit quota rapidly.

---

## Gotchas

- Cloudflare Queues guarantee **at-least-once** delivery. Even with an idempotency guard in D1, there is a short window between the `SELECT` and `INSERT` in `claimDelivery` where two concurrent workers can both claim the same key. Add a `UNIQUE` constraint on `idempotency_key` (implied by `PRIMARY KEY`) so the second `INSERT` fails and the second worker skips the send.
- The `MESSAGE_BATCH` type requires the Worker's `queue` export to be defined at the top level, not inside a nested object, or the runtime will not invoke it for queue messages.
- `message.retry({ delaySeconds })` only delays the *next* retry, not all remaining retries. Each invocation calculates the next delay independently using the `attempts` value from D1.
- MailChannels `x-message-id` header is only present on successful 202 responses. On retried messages the same MIME `Message-ID` header set in the payload provides a relay-level dedup identifier.

---

## Verification

```bash
# Enqueue a test email
curl -X POST https://your-worker.dev/ \
  -H 'Content-Type: application/json' \
  -d '{
    "idempotencyKey": "test-001",
    "to": "test@example.com",
    "from": "hello@example.com",
    "subject": "Queue test",
    "html": "<p>It works.</p>"
  }'

# Check delivery status in D1
wrangler d1 execute email-db --command \
  "SELECT idempotency_key, status, attempts, last_error FROM email_deliveries ORDER BY queued_at DESC LIMIT 10;"

# Tail the consumer Worker logs
wrangler tail --filter-consumer email-queue
```

---

## Related

- `workers-email-template-versioning.md` — resolving HTML content before enqueuing
- `workers-email-open-tracking.md` — appending tracking pixels to `html` payload
- Cloudflare Queues docs: https://developers.cloudflare.com/queues/

---

## Sources

- https://developers.cloudflare.com/queues/reference/javascript-apis/
- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://mailchannels.zendesk.com/hc/en-us/articles/4565898358413
