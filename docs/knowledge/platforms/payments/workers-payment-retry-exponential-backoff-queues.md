# Payment Retry with Exponential Backoff via Workers Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Payment processing is inherently unreliable — gateways return transient errors, card networks time out, and fraud rules trigger false positives that clear on retry. Retrying immediately causes thundering-herd problems and is more likely to be flagged as abuse. This article implements a robust payment retry system using Cloudflare Queues with exponential backoff: failed payments are enqueued with attempt metadata, the consumer retries with delay computed as `2^attempt * 60` seconds, gives up after 5 attempts, marks the payment `permanently_failed` in D1, and posts a Slack alert so the operations team can intervene.

---

## Context

Cloudflare Queues supports `delaySeconds` on individual messages, allowing a consumer to re-enqueue a message with an increasing delay without needing an external scheduler or cron. The maximum `delaySeconds` value is 43200 (12 hours). Exponential backoff with 5 attempts gives delays of 60s, 120s, 240s, 480s, and 960s — all well within the 12-hour cap and spread enough to avoid retry storms. D1 is used to track the canonical payment record and its state machine transitions: `pending -> processing -> failed -> retry_queued -> permanently_failed`. A Slack webhook fires on final failure so human intervention is possible without polling D1.

---

## Section 1 — D1 Schema

```sql
-- migrations/0004_payment_jobs.sql
CREATE TABLE IF NOT EXISTS payment_jobs (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  customer_id     TEXT NOT NULL,
  amount          INTEGER NOT NULL,           -- Amount in smallest currency unit (cents)
  currency        TEXT NOT NULL DEFAULT 'usd',
  payment_method  TEXT NOT NULL,              -- payment_method ID or stored card reference
  status          TEXT NOT NULL DEFAULT 'pending',
  -- Status transitions: pending -> processing -> succeeded
  --                     processing -> failed -> retry_queued -> permanently_failed
  attempt_number  INTEGER NOT NULL DEFAULT 0,
  max_attempts    INTEGER NOT NULL DEFAULT 5,
  last_error      TEXT,
  next_attempt_at INTEGER,                    -- Unix timestamp
  succeeded_at    INTEGER,
  failed_at       INTEGER,                    -- Timestamp of permanent failure
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_payment_jobs_customer
  ON payment_jobs (customer_id);
CREATE INDEX IF NOT EXISTS idx_payment_jobs_status
  ON payment_jobs (status);
```

---

## Section 2 — Payment Producer (Enqueue Initial Job)

```typescript
// src/payment-producer.ts
import { Queue } from '@cloudflare/workers-types';

export interface PaymentJobMessage {
  jobId: string;
  customerId: string;
  amount: number;
  currency: string;
  paymentMethod: string;
  attemptNumber: number;
}

export interface Env {
  PAYMENT_RETRY_QUEUE: Queue<PaymentJobMessage>;
  DB: D1Database;
}

export async function enqueuePayment(
  env: Env,
  params: {
    customerId: string;
    amount: number;
    currency: string;
    paymentMethod: string;
  },
): Promise<string> {
  // Create job record in D1
  const jobId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO payment_jobs (id, customer_id, amount, currency, payment_method, status)
     VALUES (?, ?, ?, ?, ?, 'pending')`,
  )
    .bind(jobId, params.customerId, params.amount, params.currency, params.paymentMethod)
    .run();

  // Enqueue first attempt (no delay on initial attempt)
  await env.PAYMENT_RETRY_QUEUE.send({
    jobId,
    customerId: params.customerId,
    amount: params.amount,
    currency: params.currency,
    paymentMethod: params.paymentMethod,
    attemptNumber: 1,
  });

  return jobId;
}
```

---

## Section 3 — Queue Consumer with Exponential Backoff

```typescript
// src/payment-consumer.ts
import { D1Database, Queue } from '@cloudflare/workers-types';
import type { PaymentJobMessage } from './payment-producer';

export interface ConsumerEnv {
  DB: D1Database;
  PAYMENT_RETRY_QUEUE: Queue<PaymentJobMessage>;
  STRIPE_SECRET_KEY: string;
  SLACK_WEBHOOK_URL: string;
}

const MAX_ATTEMPTS = 5;

/**
 * Compute delay in seconds for attempt N using exponential backoff.
 * attempt 1 -> 60s, 2 -> 120s, 3 -> 240s, 4 -> 480s, 5 -> 960s
 */
function backoffDelay(attemptNumber: number): number {
  return Math.min(Math.pow(2, attemptNumber) * 60, 43200);
}

async function attemptCharge(
  msg: PaymentJobMessage,
  stripeKey: string,
): Promise<{ success: boolean; chargeId?: string; error?: string }> {
  const response = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${stripeKey}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      // Idempotency key prevents duplicate charges on network retries
      'Idempotency-Key': `${msg.jobId}-attempt-${msg.attemptNumber}`,
    },
    body: new URLSearchParams({
      amount: msg.amount.toString(),
      currency: msg.currency,
      payment_method: msg.paymentMethod,
      customer: msg.customerId,
      confirm: 'true',
      off_session: 'true',
    }),
  });

  if (response.ok) {
    const pi = await response.json<{ id: string; status: string }>();
    if (pi.status === 'succeeded') {
      return { success: true, chargeId: pi.id };
    }
    return { success: false, error: `Unexpected status: ${pi.status}` };
  }

  const err = await response.json<{ error: { message: string; code: string } }>();

  // Permanent failures — do not retry
  const permanentErrorCodes = [
    'card_declined',
    'stolen_card',
    'lost_card',
    'do_not_honor',
    'transaction_not_allowed',
  ];
  if (permanentErrorCodes.includes(err.error?.code)) {
    return { success: false, error: `Permanent: ${err.error.message}` };
  }

  return { success: false, error: err.error?.message ?? 'Unknown Stripe error' };
}

async function alertSlack(msg: PaymentJobMessage, lastError: string, webhookUrl: string): Promise<void> {
  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `:x: Payment *permanently failed* after ${MAX_ATTEMPTS} attempts.`,
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: [
              `*Job ID:* ${msg.jobId}`,
              `*Customer:* ${msg.customerId}`,
              `*Amount:* ${(msg.amount / 100).toFixed(2)} ${msg.currency.toUpperCase()}`,
              `*Last error:* ${lastError}`,
              `*Attempts:* ${MAX_ATTEMPTS}`,
            ].join('\n'),
          },
        },
      ],
    }),
  });
}

export default {
  async queue(
    batch: MessageBatch<PaymentJobMessage>,
    env: ConsumerEnv,
  ): Promise<void> {
    for (const queueMsg of batch.messages) {
      const msg = queueMsg.body;

      // Mark as processing
      await env.DB.prepare(
        `UPDATE payment_jobs
         SET status = 'processing', attempt_number = ?, updated_at = unixepoch()
         WHERE id = ?`,
      ).bind(msg.attemptNumber, msg.jobId).run();

      const result = await attemptCharge(msg, env.STRIPE_SECRET_KEY);

      if (result.success) {
        await env.DB.prepare(
          `UPDATE payment_jobs
           SET status = 'succeeded', succeeded_at = unixepoch(), updated_at = unixepoch()
           WHERE id = ?`,
        ).bind(msg.jobId).run();
        queueMsg.ack();
        continue;
      }

      // Check if this error is permanent or we've exhausted attempts
      const isPermanent =
        result.error?.startsWith('Permanent:') || msg.attemptNumber >= MAX_ATTEMPTS;

      if (isPermanent) {
        await env.DB.prepare(
          `UPDATE payment_jobs
           SET status = 'permanently_failed',
               last_error = ?,
               failed_at = unixepoch(),
               updated_at = unixepoch()
           WHERE id = ?`,
        ).bind(result.error ?? 'Unknown', msg.jobId).run();

        await alertSlack(msg, result.error ?? 'Unknown', env.SLACK_WEBHOOK_URL);
        queueMsg.ack(); // Ack so the queue doesn't re-deliver endlessly
        continue;
      }

      // Transient failure — re-enqueue with backoff delay
      const delaySeconds = backoffDelay(msg.attemptNumber);
      const nextAttemptAt = Math.floor(Date.now() / 1000) + delaySeconds;

      await env.DB.prepare(
        `UPDATE payment_jobs
         SET status = 'retry_queued',
             last_error = ?,
             next_attempt_at = ?,
             updated_at = unixepoch()
         WHERE id = ?`,
      ).bind(result.error ?? 'Unknown', nextAttemptAt, msg.jobId).run();

      // Re-enqueue with incremented attempt number and computed delay
      await env.PAYMENT_RETRY_QUEUE.send(
        {
          ...msg,
          attemptNumber: msg.attemptNumber + 1,
        },
        { delaySeconds },
      );

      queueMsg.ack(); // Ack current message — next attempt is the re-enqueued one
    }
  },
};
```

---

## Anti-patterns

- **Using `msg.retry()` for backoff** — Queue's built-in `retry()` uses a fixed short delay and counts against the queue's delivery attempt limit. Re-enqueue manually with `delaySeconds` for controlled exponential backoff.
- **Not including an idempotency key on Stripe API calls** — Without `Idempotency-Key`, a network timeout between the charge succeeding and your acknowledgment can lead to double charges on retry. Key on `{jobId}-attempt-{attemptNumber}`.
- **Retrying hard declines** — Error codes like `stolen_card` or `do_not_honor` will never succeed; detect and short-circuit to `permanently_failed` immediately.
- **Alerting on every failure** — Send the Slack alert only on final permanent failure, not on transient failures, to avoid alert fatigue.
- **Infinite retry loops** — Always bound retry depth by `attemptNumber >= MAX_ATTEMPTS` checked before re-enqueuing, not only after the charge call.

---

## Gotchas

- Cloudflare Queues `delaySeconds` max is 43200 (12 hours); the 5th retry delay (960s) is well within this but verify your `MAX_ATTEMPTS` and base delay for your use case.
- `ack()` must be called even on permanent failures — not acking means the message is re-delivered by the queue after its visibility timeout, creating spurious retries.
- The `Idempotency-Key` header on Stripe is cached for 24 hours; if you replay an attempt after 24h with the same key, Stripe returns a fresh result, which is the desired behavior for next-day retries.
- `off_session: 'true'` is required for saving card charges without the cardholder present; omitting it causes authentication errors for 3DS-enrolled cards.
- D1 writes inside the consumer are not transactional with the queue ack — if the Worker crashes between the D1 update and `queueMsg.ack()`, the message will be re-delivered and processed again. Ensure your D1 status updates are idempotent (use `UPDATE ... SET status = 'processing'` which is safe to repeat).

---

## Verification

```bash
# Apply migration
npx wrangler d1 execute example project-db --file migrations/0004_payment_jobs.sql

# Deploy worker
npx wrangler deploy

# Enqueue a test payment (call your enqueuePayment endpoint)
curl -X POST https://your-worker.workers.dev/payments/enqueue \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"cus_test","amount":999,"currency":"usd","paymentMethod":"pm_card_chargeDeclined"}'

# Monitor D1 job status over time
npx wrangler d1 execute example project-db --command \
  "SELECT id, status, attempt_number, last_error, next_attempt_at FROM payment_jobs ORDER BY created_at DESC LIMIT 5;"

# Check queue metrics in Cloudflare Dashboard:
# Workers & Pages > Queues > payment-retry > Metrics
```

---

## Related

- `stripe-webhooks-workers-d1-event-deduplication.md`
- `stripe-subscription-lifecycle-workers-kv.md`
- `paddle-billing-workers-webhook-verification.md`

---

## Sources

- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Cloudflare Queues delaySeconds — https://developers.cloudflare.com/queues/configuration/message-delay/
- Stripe Idempotency Keys — https://stripe.com/docs/api/idempotent_requests
- Stripe Off-session Payments — https://stripe.com/docs/payments/save-and-reuse
- Exponential Backoff Design — https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
