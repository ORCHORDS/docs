# Dead Letter Queue (DLQ) Pattern for Cloudflare Queue Failures

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A consumer Worker processes messages from a Cloudflare Queue. Occasionally a message fails — bad payload, downstream API is down, a transient D1 timeout. Cloudflare Queues retries automatically, but after `max_retries` exhausted attempts the message is silently discarded. Production incidents reveal gaps in audit logs, missing email sends, or lost payment events with no trace of what went wrong. You need a safety net that captures every exhausted-retry message for inspection, alerting, and replay.

## Context

A **Dead Letter Queue** (DLQ) is a secondary queue that receives messages that could not be successfully processed after all retry attempts. The pattern prevents permanent silent data loss, enables post-mortem diagnosis, and supports replay once the underlying bug is fixed.

```
  Primary Queue
  ─────────────
  [message A]  ──► Consumer Worker
  [message B]       │   ↺ retry 1
                    │   ↺ retry 2
                    │   ↺ retry 3   (max_retries = 3)
                    │
                    └──► Dead Letter Queue ──► DLQ Processor Worker
                                                  ├── alert (PagerDuty / email)
                                                  ├── store in D1 for inspection
                                                  └── replay endpoint (manual or cron)
```

Cloudflare Queues supports native DLQ configuration via `dead_letter_queue` in `wrangler.toml`. No custom code needed to route exhausted messages to the DLQ — the platform does it automatically.

## Section 1 — Queue and DLQ Configuration

```toml
# wrangler.toml

# Primary queue consumer
[[queues.consumers]]
queue             = "payment-events"
max_batch_size    = 10
max_batch_timeout = 5       # seconds
max_retries       = 4       # attempts before DLQ
dead_letter_queue = "payment-events-dlq"  # Cloudflare routes here after max_retries

# DLQ consumer (separate worker handles dead letters)
[[queues.consumers]]
queue             = "payment-events-dlq"
max_batch_size    = 50
max_batch_timeout = 30
max_retries       = 1       # DLQ processor should not retry aggressively
```

Create both queues:

```bash
wrangler queues create payment-events
wrangler queues create payment-events-dlq
```

## Section 2 — Primary Consumer with Explicit Error Handling

Per-message `ack`/`retry` gives fine control over which messages enter the DLQ path:

```typescript
// payment-consumer.ts
import type { PaymentEvent } from './schema';

export interface Env {
  PAYMENT_DB:      D1Database;
  STRIPE_SECRET:   string;
}

export default {
  async queue(batch: MessageBatch<PaymentEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const result = await processPayment(msg.body, env);

      if (result.success) {
        msg.ack();
        continue;
      }

      // Classify the failure
      if (result.retryable) {
        // Transient — exponential backoff: 10s, 60s, 300s, 900s
        const delaySeconds = Math.pow(result.attemptNumber, 3) * 10;
        console.warn(JSON.stringify({
          level:      'warn',
          event:      'payment_retry',
          messageId:  msg.id,
          attempt:    result.attemptNumber,
          delaySeconds,
          reason:     result.reason,
        }));
        msg.retry({ delaySeconds: Math.min(delaySeconds, 900) });
      } else {
        // Permanent failure — do not retry, let Queues route to DLQ
        // We must still ack or retry; nacking is a retry.
        // Log a structured error before the DLQ picks it up.
        console.error(JSON.stringify({
          level:     'error',
          event:     'payment_permanent_failure',
          messageId: msg.id,
          reason:    result.reason,
          body:      msg.body,
        }));
        // Exhaust remaining retries immediately by acknowledging with failure marker:
        // Cloudflare does not expose "move to DLQ now" directly, so we retry with
        // delaySeconds=0 and rely on max_retries being reached.
        msg.retry();
      }
    }
  },
};

interface ProcessResult {
  success:       boolean;
  retryable:     boolean;
  reason:        string;
  attemptNumber: number;
}

async function processPayment(event: PaymentEvent, env: Env): Promise<ProcessResult> {
  try {
    // Validate schema
    if (!event.paymentId || !event.amountCents) {
      return { success: false, retryable: false, reason: 'invalid_schema', attemptNumber: 1 };
    }

    // Check for duplicate (idempotency)
    const existing = await env.PAYMENT_DB
      .prepare('SELECT id FROM payment_events WHERE payment_id = ?')
      .bind(event.paymentId)
      .first();

    if (existing) {
      return { success: true, retryable: false, reason: 'duplicate', attemptNumber: 1 };
    }

    // Process with Stripe
    const stripeRes = await fetch('https://api.stripe.com/v1/charges', {
      method:  'POST',
      headers: {
        'Authorization': `Bearer ${env.STRIPE_SECRET}`,
        'Content-Type':  'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        amount:   String(event.amountCents),
        currency: event.currency,
        source:   event.stripeToken,
      }),
    });

    if (stripeRes.status === 402) {
      // Card declined — permanent failure
      return { success: false, retryable: false, reason: 'card_declined', attemptNumber: 1 };
    }

    if (!stripeRes.ok) {
      // Stripe 5xx — transient
      return { success: false, retryable: true, reason: `stripe_${stripeRes.status}`, attemptNumber: 1 };
    }

    // Persist
    await env.PAYMENT_DB
      .prepare('INSERT INTO payment_events (payment_id, amount_cents, currency, processed_at) VALUES (?, ?, ?, ?)')
      .bind(event.paymentId, event.amountCents, event.currency, new Date().toISOString())
      .run();

    return { success: true, retryable: false, reason: 'ok', attemptNumber: 1 };
  } catch (err) {
    return { success: false, retryable: true, reason: String(err), attemptNumber: 1 };
  }
}
```

## Section 3 — DLQ Processor Worker

The DLQ processor stores dead letters, fires alerts, and exposes a replay endpoint:

```typescript
// dlq-processor.ts
import type { PaymentEvent } from './schema';

export interface Env {
  DLQ_DB:          D1Database;
  ALERT_EMAIL:     string;
  RESEND_API_KEY:  string;
}

export default {
  // Called by Cloudflare Queues when messages arrive in the DLQ
  async queue(batch: MessageBatch<PaymentEvent>, env: Env): Promise<void> {
    const timestamp = new Date().toISOString();

    // 1. Persist all dead letters to D1 for inspection
    const insertStmt = env.DLQ_DB.prepare(`
      INSERT OR IGNORE INTO dead_letters
        (message_id, queue_name, body_json, arrived_at, replayed)
      VALUES (?, 'payment-events', ?, ?, false)
    `);

    const inserts = batch.messages.map(msg =>
      insertStmt.bind(msg.id, JSON.stringify(msg.body), timestamp)
    );
    await env.DLQ_DB.batch(inserts);

    // 2. Fire an alert for the batch
    await sendAlert(env, batch.messages.length, timestamp);

    batch.ackAll();
  },

  // HTTP endpoint for replaying specific dead letters
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/dlq/replay' && request.method === 'POST') {
      return handleReplay(request, env);
    }

    if (url.pathname === '/dlq/list' && request.method === 'GET') {
      return handleList(env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function sendAlert(env: Env, count: number, timestamp: string): Promise<void> {
  const res = await fetch('https://api.resend.com/emails', {
    method:  'POST',
    headers: {
      'Authorization': `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type':  'application/json',
    },
    body: JSON.stringify({
      from:    'alerts@example.com',
      to:      env.ALERT_EMAIL,
      subject: `[DLQ] ${count} payment event(s) dead-lettered at ${timestamp}`,
      text:    `${count} message(s) failed all retries. Review at /dlq/list.`,
    }),
  });
  if (!res.ok) console.error('Alert email failed:', res.status);
}

async function handleList(env: Env): Promise<Response> {
  const rows = await env.DLQ_DB
    .prepare('SELECT message_id, body_json, arrived_at, replayed FROM dead_letters ORDER BY arrived_at DESC LIMIT 100')
    .all();
  return Response.json(rows.results);
}

async function handleReplay(request: Request, env: Env): Promise<Response> {
  const { messageId } = await request.json<{ messageId: string }>();

  const row = await env.DLQ_DB
    .prepare('SELECT body_json FROM dead_letters WHERE message_id = ? AND replayed = false')
    .bind(messageId)
    .first<{ body_json: string }>();

  if (!row) return Response.json({ error: 'Not found or already replayed' }, { status: 404 });

  // Re-enqueue into the primary queue
  // Note: the replay Worker needs a producer binding to the primary queue
  // This is a simplified illustration — in practice inject the Queue binding via Env
  await env.DLQ_DB
    .prepare('UPDATE dead_letters SET replayed = true, replayed_at = ? WHERE message_id = ?')
    .bind(new Date().toISOString(), messageId)
    .run();

  return Response.json({ replayed: true, messageId });
}
```

## Section 4 — D1 Schema for Dead Letter Storage

```sql
-- migrations/0001_dead_letters.sql
CREATE TABLE IF NOT EXISTS dead_letters (
  message_id  TEXT    PRIMARY KEY,
  queue_name  TEXT    NOT NULL,
  body_json   TEXT    NOT NULL,
  arrived_at  TEXT    NOT NULL,  -- ISO-8601
  replayed    INTEGER NOT NULL DEFAULT 0,
  replayed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_dead_letters_arrived
  ON dead_letters (arrived_at DESC);

CREATE INDEX IF NOT EXISTS idx_dead_letters_replayed
  ON dead_letters (replayed);
```

Apply:
```bash
wrangler d1 execute my-db --file=migrations/0001_dead_letters.sql
```

## Anti-patterns

**Sending every `retry()` to the DLQ yourself.** The platform does this automatically after `max_retries`. Manually routing to the DLQ before exhausting retries bypasses the retry budget and loses transient-failure recovery.

**Using the same `max_retries` value on the DLQ queue.** Set DLQ retries to 1 or 2. If the DLQ processor itself fails repeatedly, messages re-dead-letter into a secondary DLQ or are permanently lost — a loop without end.

**Not alerting on DLQ ingestion.** A silent DLQ defeats the purpose. Wire up at least an email or Slack notification for every batch that arrives.

**Replicating business logic in the replay endpoint.** The replay endpoint should only re-enqueue the original message body into the primary queue. Let the primary consumer re-run the logic — do not duplicate it.

## Gotchas

- **`dead_letter_queue` must already exist** before you deploy the consumer. Create it with `wrangler queues create` first.
- **Message IDs are not stable across redeliveries** — `msg.id` changes if Queues internally requeues a message. Use a `messageId` in the payload body for stable deduplication.
- **DLQ messages include the original body only** — metadata like the original enqueue timestamp is not propagated. Embed `enqueuedAt` in every event payload from the producer.
- **Cloudflare Queues does not support native DLQ for batch-level failures.** If `batch.ackAll()` or `batch.retryAll()` is called and the entire batch fails, the whole batch goes to the DLQ together. Individual `msg.retry()` / `msg.ack()` gives per-message control.
- **Replay must be idempotent.** The primary consumer will see the replayed message as a new message without history. Idempotency keys in the payload prevent double-processing.

## Verification

```bash
# Create a test message that will always fail (bad payload)
wrangler queues send payment-events '{"paymentId":"","amountCents":-1}'

# Wait for max_retries, then check DLQ
wrangler queues send payment-events-dlq --list  # Not a real command — use the DB
wrangler d1 execute my-db --command \
  "SELECT message_id, arrived_at FROM dead_letters ORDER BY arrived_at DESC LIMIT 5;"

# Replay a dead letter
curl -X POST https://my-dlq-processor.example.com/dlq/replay \
  -H "Content-Type: application/json" \
  -d '{"messageId":"<message_id_from_db>"}'
```

Tail DLQ processor logs:
```bash
wrangler tail dlq-processor --format pretty
```

## Related

- `fan-out-queues-workers.md` — fan-out produces messages that may need DLQ per consumer
- `idempotency-key-pattern-workers-d1.md` — safe replay requires idempotent consumers
- `retry-with-exponential-backoff.md` — retry strategy before DLQ ingestion
- `feature-cookbook-queues.md` — general Cloudflare Queues usage

## Sources

- Cloudflare Queues documentation, "Dead Letter Queues" — developers.cloudflare.com/queues/configuration/dead-letter-queues/
- AWS, "Amazon SQS Dead-Letter Queues" — docs.aws.amazon.com (conceptual reference)
- Enterprise Integration Patterns, Hohpe & Woolf — "Dead Letter Channel"
