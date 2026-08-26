# Payment Retry Logic with Exponential Backoff via Cloudflare Queues

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A subscription payment fails — card declined, insufficient funds, network timeout. Stripe's built-in Smart Retries work for `invoice.payment_failed` events, but they are a black box: you cannot inject business logic between retries (pause account, send custom email at attempt 2, escalate to support at attempt 4), and you cannot unify retry behaviour across multiple payment providers (Stripe + PayPal + NowPayments). Teams that need full control over the retry schedule, side-effects, and dead-letter handling should own the retry loop themselves using **Cloudflare Queues** as the durable message bus.

---

## Context

Cloudflare Queues (GA 2024) provides at-least-once delivery with configurable retry delay and dead-letter queues (DLQ). A Worker can enqueue a message and then consume it after a delay — effectively implementing a scheduled job without Cron Triggers. Combined with Cloudflare D1 for state tracking and KV for per-customer retry counters, you get a fully serverless, edge-native payment retry system with no extra infrastructure.

**Key properties:**

| Property | Value |
|---|---|
| Message visibility timeout | 12 hours max |
| Retry delay (delaySeconds) | Up to 43,200 s |
| Max delivery attempts | Configurable (default 3) |
| DLQ | Separate queue binding |
| Batch size | Up to 100 messages / batch |

---

## Architecture Overview

```
Stripe webhook (invoice.payment_failed)
        │
        ▼
[Worker: webhook-receiver]
  • verify signature
  • insert payment_retries row (D1)
  • enqueue RetryJob with delay=0
        │
        ▼
[Queue: payment-retry-queue]
        │
        ▼
[Worker: retry-consumer]
  • load attempt number from D1
  • attempt Stripe.paymentIntents.confirm()
  • success → mark resolved, send success email
  • failure → compute next delay, re-enqueue OR move to DLQ
        │
        ▼
[DLQ: payment-retry-dlq]
  • alert ops, pause account, open support ticket
```

---

## D1 Schema

```sql
-- migration: 0001_payment_retries.sql
CREATE TABLE IF NOT EXISTS payment_retries (
  id            TEXT PRIMARY KEY,          -- UUID
  invoice_id    TEXT NOT NULL,
  customer_id   TEXT NOT NULL,
  payment_intent_id TEXT NOT NULL,
  amount        INTEGER NOT NULL,          -- cents
  currency      TEXT NOT NULL DEFAULT 'usd',
  attempt       INTEGER NOT NULL DEFAULT 0,
  max_attempts  INTEGER NOT NULL DEFAULT 5,
  status        TEXT NOT NULL DEFAULT 'pending', -- pending|succeeded|failed|exhausted
  last_error    TEXT,
  next_retry_at TEXT,                      -- ISO8601
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_payment_retries_invoice ON payment_retries(invoice_id);
CREATE INDEX idx_payment_retries_status  ON payment_retries(status);
CREATE INDEX idx_payment_retries_customer ON payment_retries(customer_id);
```

---

## Wrangler Configuration

```toml
# wrangler.toml
name = "payment-retry-worker"
compatibility_date = "2025-01-01"

[[queues.producers]]
binding  = "RETRY_QUEUE"
queue    = "payment-retry-queue"

[[queues.consumers]]
queue             = "payment-retry-queue"
max_batch_size    = 10
max_batch_timeout = 5
max_retries       = 1          # let our own logic handle retries
dead_letter_queue = "payment-retry-dlq"

[[queues.consumers]]
queue          = "payment-retry-dlq"
max_batch_size = 10

[[d1_databases]]
binding      = "DB"
database_name = "payments"
database_id  = "YOUR_D1_DATABASE_ID"

[vars]
STRIPE_WEBHOOK_SECRET = "whsec_..."   # use Secrets in prod: wrangler secret put
STRIPE_SECRET_KEY     = "sk_live_..." # use Secrets in prod
```

---

## Retry Message Type

```typescript
// types/retry.ts
export interface RetryJob {
  retryId: string;       // payment_retries.id
  invoiceId: string;
  paymentIntentId: string;
  customerId: string;
  attempt: number;
}

export const MAX_ATTEMPTS = 5;

// Exponential backoff schedule (seconds):
// Attempt 1: 30 min  → 1800
// Attempt 2: 2 h     → 7200
// Attempt 3: 8 h     → 28800
// Attempt 4: 24 h    → 86400
// Attempt 5: dead-letter
export function backoffSeconds(attempt: number): number {
  const schedule = [1800, 7200, 28800, 86400];
  return schedule[Math.min(attempt - 1, schedule.length - 1)];
}
```

---

## Webhook Receiver Worker

```typescript
// workers/webhook-receiver.ts
import Stripe from 'stripe';
import { RetryJob } from '../types/retry';

export interface Env {
  DB: D1Database;
  RETRY_QUEUE: Queue<RetryJob>;
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_SECRET_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    const sig = request.headers.get('stripe-signature') ?? '';
    const body = await request.text();

    let event: Stripe.Event;
    try {
      event = await new Stripe(env.STRIPE_SECRET_KEY).webhooks.constructEventAsync(
        body, sig, env.STRIPE_WEBHOOK_SECRET
      );
    } catch (err) {
      return new Response(`Webhook signature verification failed: ${err}`, { status: 400 });
    }

    if (event.type === 'invoice.payment_failed') {
      await handlePaymentFailed(event.data.object as Stripe.Invoice, env);
    }

    return new Response('ok', { status: 200 });
  },
};

async function handlePaymentFailed(invoice: Stripe.Invoice, env: Env) {
  const retryId = crypto.randomUUID();
  const paymentIntentId = typeof invoice.payment_intent === 'string'
    ? invoice.payment_intent
    : invoice.payment_intent?.id ?? '';

  // Insert initial retry record
  await env.DB.prepare(`
    INSERT INTO payment_retries
      (id, invoice_id, customer_id, payment_intent_id, amount, currency, attempt, status)
    VALUES (?, ?, ?, ?, ?, ?, 0, 'pending')
    ON CONFLICT(invoice_id) DO NOTHING
  `).bind(
    retryId,
    invoice.id,
    typeof invoice.customer === 'string' ? invoice.customer : invoice.customer?.id ?? '',
    paymentIntentId,
    invoice.amount_due,
    invoice.currency,
  ).run();

  // Fetch the actual record (handles ON CONFLICT case)
  const row = await env.DB.prepare(
    'SELECT * FROM payment_retries WHERE invoice_id = ?'
  ).bind(invoice.id).first<{ id: string; attempt: number; status: string }>();

  if (!row || row.status !== 'pending') return; // already succeeded or exhausted

  const job: RetryJob = {
    retryId: row.id,
    invoiceId: invoice.id,
    paymentIntentId,
    customerId: typeof invoice.customer === 'string' ? invoice.customer : '',
    attempt: row.attempt,
  };

  // Enqueue immediately for first attempt
  await env.RETRY_QUEUE.send(job, { delaySeconds: 0 });
}
```

---

## Retry Consumer Worker

```typescript
// workers/retry-consumer.ts
import Stripe from 'stripe';
import { RetryJob, MAX_ATTEMPTS, backoffSeconds } from '../types/retry';

export interface Env {
  DB: D1Database;
  RETRY_QUEUE: Queue<RetryJob>;
  STRIPE_SECRET_KEY: string;
  NOTIFICATION_URL: string; // internal endpoint for alerts/emails
}

export default {
  async queue(batch: MessageBatch<RetryJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processRetry(msg.body, env);
        msg.ack();
      } catch (err) {
        // Unhandled error: let Queues retry via its own retry policy (max_retries=1)
        msg.retry();
      }
    }
  },
};

async function processRetry(job: RetryJob, env: Env): Promise<void> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  // Load current state
  const row = await env.DB.prepare(
    'SELECT * FROM payment_retries WHERE id = ?'
  ).bind(job.retryId).first<{
    id: string; attempt: number; max_attempts: number; status: string;
    payment_intent_id: string; customer_id: string; invoice_id: string;
  }>();

  if (!row || row.status !== 'pending') return; // already resolved

  const attempt = row.attempt + 1;

  // Mark in-progress
  await env.DB.prepare(
    'UPDATE payment_retries SET attempt = ?, updated_at = datetime("now") WHERE id = ?'
  ).bind(attempt, row.id).run();

  let succeeded = false;
  let errorMessage = '';

  try {
    const pi = await stripe.paymentIntents.confirm(row.payment_intent_id, {
      payment_method: await getDefaultPaymentMethod(stripe, row.customer_id),
    });
    succeeded = pi.status === 'succeeded';
  } catch (err: unknown) {
    errorMessage = err instanceof Error ? err.message : String(err);
  }

  if (succeeded) {
    await env.DB.prepare(
      `UPDATE payment_retries
       SET status = 'succeeded', updated_at = datetime('now')
       WHERE id = ?`
    ).bind(row.id).run();

    await notify(env.NOTIFICATION_URL, {
      type: 'payment_retry_succeeded',
      customerId: row.customer_id,
      invoiceId: row.invoice_id,
      attempt,
    });
    return;
  }

  // Failed — schedule next retry or exhaust
  if (attempt >= row.max_attempts) {
    await env.DB.prepare(
      `UPDATE payment_retries
       SET status = 'exhausted', last_error = ?, updated_at = datetime('now')
       WHERE id = ?`
    ).bind(errorMessage, row.id).run();

    await notify(env.NOTIFICATION_URL, {
      type: 'payment_retry_exhausted',
      customerId: row.customer_id,
      invoiceId: row.invoice_id,
      attempt,
      error: errorMessage,
    });
    return;
  }

  // Re-enqueue with backoff delay
  const delay = backoffSeconds(attempt);
  const nextRetryAt = new Date(Date.now() + delay * 1000).toISOString();

  await env.DB.prepare(
    `UPDATE payment_retries
     SET last_error = ?, next_retry_at = ?, updated_at = datetime('now')
     WHERE id = ?`
  ).bind(errorMessage, nextRetryAt, row.id).run();

  const nextJob: RetryJob = { ...job, attempt };
  await (env.RETRY_QUEUE as Queue<RetryJob>).send(nextJob, { delaySeconds: delay });

  await notify(env.NOTIFICATION_URL, {
    type: 'payment_retry_scheduled',
    customerId: row.customer_id,
    invoiceId: row.invoice_id,
    attempt,
    nextRetryAt,
    error: errorMessage,
  });
}

async function getDefaultPaymentMethod(
  stripe: Stripe,
  customerId: string
): Promise<string> {
  const customer = await stripe.customers.retrieve(customerId) as Stripe.Customer;
  const pm = customer.invoice_settings?.default_payment_method;
  if (!pm) throw new Error(`No default payment method for customer ${customerId}`);
  return typeof pm === 'string' ? pm : pm.id;
}

async function notify(url: string, payload: unknown): Promise<void> {
  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
```

---

## Dead-Letter Queue Handler

```typescript
// workers/dlq-handler.ts
import { RetryJob } from '../types/retry';

export interface Env {
  DB: D1Database;
  PAGERDUTY_KEY: string;
}

export default {
  async queue(batch: MessageBatch<RetryJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;

      // Final mark in D1
      await env.DB.prepare(
        `UPDATE payment_retries SET status = 'exhausted', updated_at = datetime('now')
         WHERE id = ?`
      ).bind(job.retryId).run();

      // Alert ops via PagerDuty Events API v2
      await fetch('https://events.pagerduty.com/v2/enqueue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          routing_key: env.PAGERDUTY_KEY,
          event_action: 'trigger',
          payload: {
            summary: `Payment retry exhausted: invoice ${job.invoiceId}`,
            severity: 'error',
            source: 'payment-retry-dlq',
            custom_details: job,
          },
        }),
      });

      msg.ack();
    }
  },
};
```

---

## Observability: Querying Retry State

```typescript
// Example D1 queries for dashboards / support tooling

// All retries in-flight
const inFlight = await env.DB.prepare(
  `SELECT customer_id, invoice_id, attempt, max_attempts, next_retry_at, last_error
   FROM payment_retries WHERE status = 'pending' ORDER BY next_retry_at`
).all();

// Exhausted in last 7 days (revenue at risk)
const exhausted = await env.DB.prepare(
  `SELECT customer_id, invoice_id, amount, currency, attempt, last_error
   FROM payment_retries
   WHERE status = 'exhausted'
     AND updated_at >= datetime('now', '-7 days')
   ORDER BY updated_at DESC`
).all();

// Recovery rate by attempt number
const recoveryRate = await env.DB.prepare(
  `SELECT attempt,
          SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS recovered,
          COUNT(*) AS total
   FROM payment_retries
   WHERE created_at >= datetime('now', '-30 days')
   GROUP BY attempt`
).all();
```

---

## Anti-patterns

- **Using Stripe Smart Retries AND this queue**: Double-retrying the same payment intent causes duplicate charges and confusing audit logs. Disable Smart Retries on the Stripe subscription when using this system (`collection_method: 'charge_automatically'`, `payment_settings.save_default_payment_method: 'off'` and Smart Retry turned off in Dashboard).

- **Enqueueing without idempotency guard**: If the webhook fires twice (Stripe guarantees at-least-once), two retry chains start for the same invoice. Use `ON CONFLICT(invoice_id) DO NOTHING` in the insert and always load state from D1 before acting.

- **Hardcoding `delaySeconds` above the 43,200-second cap**: Queues silently clamps values. Verify your schedule with `Math.min(delay, 43200)`.

- **Retrying 402 card errors immediately**: A declined card at attempt+0 will decline again in milliseconds. Always respect the backoff even on the first retry.

- **Not acking on business-logic exhaustion**: If you `msg.retry()` after writing `status = 'exhausted'`, the consumer refires and re-processes an already-closed record. Ack explicitly after marking exhausted.

---

## Gotchas

1. **Queue consumer and producer can share the same Worker script** but must be separate `[[queues.consumers]]` entries per queue binding.

2. **`delaySeconds` is relative to send time**, not to when the message enters the queue. Clock skew is irrelevant.

3. **Queues does not guarantee ordering** within a batch. Do not rely on processing order; always read authoritative state from D1.

4. **D1 `ON CONFLICT` requires a UNIQUE constraint**, not just a PRIMARY KEY on a different column. Add `UNIQUE(invoice_id)` explicitly.

5. **Stripe `paymentIntents.confirm` requires a payment method argument** when the original payment method was not saved to the customer. Always call `stripe.customers.retrieve` first to get `invoice_settings.default_payment_method`.

6. **DLQ messages include the original message body** (your `RetryJob`), not Stripe objects. Keep the job payload self-contained.

7. **`max_retries` in `wrangler.toml` consumer config** is the number of times Queues re-delivers on unhandled exceptions — separate from your application-level attempt counter. Set `max_retries = 1` to avoid the consumer itself retrying on top of your backoff logic.

---

## Verification

```bash
# Deploy both workers
wrangler deploy --config wrangler.toml

# Trigger a test payment failure
stripe trigger invoice.payment_failed --api-key sk_test_...

# Watch retry state in D1
wrangler d1 execute payments --command \
  "SELECT id, attempt, status, next_retry_at, last_error FROM payment_retries ORDER BY created_at DESC LIMIT 5"

# Inspect the queue
wrangler queues consumer list payment-retry-queue

# Force a DLQ message (set max_attempts=1 in D1 row, re-enqueue)
wrangler d1 execute payments --command \
  "UPDATE payment_retries SET max_attempts = 1 WHERE status = 'pending' LIMIT 1"
```

**Expected state progression:**

| Time | D1 status | attempt | Queue message |
|---|---|---|---|
| T+0 | pending | 0 | sent (delay=0) |
| T+0 | pending | 1 | re-sent (delay=1800) |
| T+30m | pending | 2 | re-sent (delay=7200) |
| T+2.5h | pending | 3 | re-sent (delay=28800) |
| T+10.5h | pending | 4 | re-sent (delay=86400) |
| T+34.5h | exhausted | 5 | DLQ |

---

## Related

- `stripe-smart-retries.md` — Stripe's built-in dunning (alternative to this pattern)
- `stripe-failed-payment-retry.md` — PaymentIntent confirm flow
- `stripe-webhook-idempotency-workers.md` — Idempotency guard for the webhook receiver
- `dunning-email-sequences.md` — Email side-effects triggered alongside retries
- `payment-state-machine-design.md` — How payment states map to retry transitions

---

## Sources

- [Cloudflare Queues documentation](https://developers.cloudflare.com/queues/)
- [Cloudflare Queues — delayed delivery](https://developers.cloudflare.com/queues/configuration/delay-messages/)
- [Cloudflare D1 — Workers binding](https://developers.cloudflare.com/d1/worker-api/)
- [Stripe — invoice.payment_failed event](https://docs.stripe.com/api/events/types#event_types-invoice.payment_failed)
- [Stripe — PaymentIntents confirm](https://docs.stripe.com/api/payment_intents/confirm)
- [Stripe Smart Retries](https://docs.stripe.com/billing/revenue-recovery/smart-retries)
