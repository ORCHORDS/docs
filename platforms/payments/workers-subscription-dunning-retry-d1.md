# Subscription Dunning & Retry Logic with D1 and Cloudflare Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A subscription payment fails (insufficient funds or expired card). Instead of immediately cancelling the subscription, you need an exponential retry schedule - day 1, day 3, day 7 - with a final cancellation after max attempts and automated grace-period notifications.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Queue: Cloudflare Queues (producer + consumer)
- Database: D1 for attempt tracking and subscription state
- Triggered by: Stripe `invoice.payment_failed` webhook
- Cancellation after: 3 failed attempts (configurable)

---

## Step 1 - D1 Schema

```sql
-- migrations/0002_dunning.sql
CREATE TABLE IF NOT EXISTS subscriptions (
  subscription_id TEXT PRIMARY KEY,
  customer_id     TEXT NOT NULL,
  customer_email  TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'active',  -- active | past_due | cancelled
  plan_id         TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payment_attempts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  subscription_id TEXT NOT NULL,
  invoice_id      TEXT NOT NULL,
  attempt_number  INTEGER NOT NULL DEFAULT 1,
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending | succeeded | failed
  next_retry_at   TEXT,
  attempted_at    TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_sub ON payment_attempts(subscription_id);
CREATE INDEX IF NOT EXISTS idx_attempts_invoice ON payment_attempts(invoice_id);
```

---

## Step 2 - Queue Producer

```typescript
// src/dunning/producer.ts
import type { Queue } from '@cloudflare/workers-types';

export interface DunningMessage {
  subscriptionId: string;
  invoiceId: string;
  customerId: string;
  customerEmail: string;
  attemptNumber: number;
}

const RETRY_DELAYS_DAYS = [1, 3, 7] as const;
export const MAX_ATTEMPTS = RETRY_DELAYS_DAYS.length;

export function nextRetryDelaySeconds(attemptNumber: number): number {
  const idx = Math.min(attemptNumber - 1, RETRY_DELAYS_DAYS.length - 1);
  return RETRY_DELAYS_DAYS[idx] * 86_400;
}

export async function enqueueRetry(
  queue: Queue<DunningMessage>,
  message: DunningMessage
): Promise<void> {
  const delaySeconds = nextRetryDelaySeconds(message.attemptNumber);
  await queue.send(message, { delaySeconds });
}
```

---

## Step 3 - Webhook Handler

```typescript
// src/index.ts (webhook route)
import { enqueueRetry, MAX_ATTEMPTS } from './dunning/producer';
import type { Queue } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  DUNNING_QUEUE: Queue;
  STRIPE_WEBHOOK_SECRET: string;
}

export async function handleInvoiceFailed(
  event: {
    data: {
      object: {
        id: string;
        subscription: string;
        customer: string;
        customer_email: string;
      };
    };
  },
  env: Env
): Promise<void> {
  const invoice = event.data.object;
  const subId = invoice.subscription;

  await env.DB
    .prepare(
      `INSERT INTO subscriptions (subscription_id, customer_id, customer_email, status, plan_id)
       VALUES (?, ?, ?, 'past_due', 'unknown')
       ON CONFLICT(subscription_id) DO UPDATE
       SET status='past_due', updated_at=datetime('now')`
    )
    .bind(subId, invoice.customer, invoice.customer_email)
    .run();

  const row = await env.DB
    .prepare(
      `SELECT COUNT(*) as cnt FROM payment_attempts
       WHERE invoice_id = ? AND status = 'failed'`
    )
    .bind(invoice.id)
    .first<{ cnt: number }>();

  const attemptNumber = (row?.cnt ?? 0) + 1;

  await env.DB
    .prepare(
      `INSERT INTO payment_attempts
       (subscription_id, invoice_id, attempt_number, status, attempted_at)
       VALUES (?, ?, ?, 'failed', datetime('now'))`
    )
    .bind(subId, invoice.id, attemptNumber)
    .run();

  if (attemptNumber >= MAX_ATTEMPTS) {
    await env.DB
      .prepare(
        `UPDATE subscriptions SET status='cancelled', updated_at=datetime('now')
         WHERE subscription_id=?`
      )
      .bind(subId)
      .run();
    console.log(`Subscription ${subId} cancelled after ${attemptNumber} failed attempts`);
    return;
  }

  await enqueueRetry(env.DUNNING_QUEUE, {
    subscriptionId: subId,
    invoiceId: invoice.id,
    customerId: invoice.customer,
    customerEmail: invoice.customer_email,
    attemptNumber: attemptNumber + 1,
  });
}
```

---

## Step 4 - Queue Consumer

```typescript
// src/dunning/consumer.ts
import type { MessageBatch } from '@cloudflare/workers-types';
import type { DunningMessage } from './producer';

interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
}

async function retryStripeInvoice(
  invoiceId: string,
  stripeKey: string
): Promise<{ status: string }> {
  const res = await fetch(
    `https://api.stripe.com/v1/invoices/${invoiceId}/pay`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${stripeKey}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    }
  );
  const data = await res.json() as { status: string; error?: { message: string } };
  if (!res.ok) throw new Error(data.error?.message ?? 'Stripe error');
  return data;
}

export default {
  async queue(
    batch: MessageBatch<DunningMessage>,
    env: Env
  ): Promise<void> {
    for (const message of batch.messages) {
      const { subscriptionId, invoiceId, attemptNumber } = message.body;

      try {
        const result = await retryStripeInvoice(invoiceId, env.STRIPE_SECRET_KEY);

        await env.DB
          .prepare(
            `UPDATE payment_attempts
             SET status = ?, attempted_at = datetime('now')
             WHERE invoice_id = ? AND attempt_number = ?`
          )
          .bind(
            result.status === 'paid' ? 'succeeded' : 'failed',
            invoiceId,
            attemptNumber
          )
          .run();

        if (result.status === 'paid') {
          await env.DB
            .prepare(
              `UPDATE subscriptions SET status='active', updated_at=datetime('now')
               WHERE subscription_id=?`
            )
            .bind(subscriptionId)
            .run();
        }

        message.ack();
      } catch (err) {
        console.error(`Retry failed for ${invoiceId} attempt ${attemptNumber}:`, err);
        message.retry();
      }
    }
  },
};
```

---

## Step 5 - wrangler.toml Queue Binding

```toml
# wrangler.toml
[[queues.producers]]
binding = "DUNNING_QUEUE"
queue = "subscription-dunning"

[[queues.consumers]]
queue = "subscription-dunning"
max_batch_size = 10
max_batch_timeout = 30
```

---

## Anti-patterns

- Do not retry synchronously inside the webhook handler - this blocks the response and risks Stripe timeout (> 30 s).
- Do not use Worker cron triggers for retries - Queues delay is more precise and avoids scan-all-rows patterns.
- Never cancel the subscription after the first failure; grace periods reduce churn.
- Avoid storing `customer_email` only in the queue message - always persist to D1 for audit.

## Gotchas

- Cloudflare Queues `delaySeconds` is capped at 43 200 s (12 hours) per enqueue; for multi-day delays, re-enqueue with additional delay from the consumer.
- The consumer `message.retry()` requeues with the Queue's own backoff, not your dunning schedule - only call it on transient errors.
- Stripe `invoices/{id}/pay` returns 402 if payment still fails; catch this and mark as `failed`, not transient.
- D1 `ON CONFLICT DO UPDATE` requires a unique constraint on the conflict column.

## Verification

```bash
# Apply schema
wrangler d1 migrations apply DB --env production

# Create the queue
wrangler queues create subscription-dunning

# Trigger a test invoice.payment_failed event
stripe trigger invoice.payment_failed

# Check attempt was recorded
wrangler d1 execute DB --env production \
  --command "SELECT * FROM payment_attempts ORDER BY created_at DESC LIMIT 5"

# Check subscription status
wrangler d1 execute DB --env production \
  --command "SELECT subscription_id, status FROM subscriptions ORDER BY updated_at DESC LIMIT 5"
```

## Related

- `documentation/categories/payments/stripe-payment-link-webhook-fulfillment-workers.md`
- `documentation/categories/payments/workers-klarna-order-management-webhook.md`

## Sources

- https://stripe.com/docs/billing/subscriptions/overview#subscription-lifecycle
- https://stripe.com/docs/api/invoices/pay
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/batching-retries/
