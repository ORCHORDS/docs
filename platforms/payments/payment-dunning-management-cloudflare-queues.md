# Payment Dunning Management with Cloudflare Queues

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Subscription platforms face involuntary churn when payment methods expire or temporarily lack funds. A structured dunning sequence — retrying charges at increasing intervals while notifying customers — recovers 15–30% of failed payments that would otherwise lapse. Manual retry logic scattered across cron jobs is fragile and cannot track per-customer grace-period state.

## Context

Cloudflare Queues delivers messages with configurable delay, making it a natural fit for scheduled dunning retries without a separate job scheduler. Each failed Stripe payment pushes a message with an exponential backoff delay. A Durable Object per subscription holds grace-period state and cancels itself when a retry succeeds. D1 stores every dunning attempt for analytics and support visibility.

## Scheduling Retries with Exponential Backoff via Queues

When Stripe fires `invoice.payment_failed`, a Worker enqueues the first retry message. The consumer re-enqueues with doubled delay on each subsequent failure up to a configurable maximum attempt count.

```typescript
// src/dunning/enqueue.ts
export interface DunningMessage {
  invoiceId: string;
  customerId: string;
  subscriptionId: string;
  attempt: number;        // 1-indexed
  maxAttempts: number;
}

const BACKOFF_SECONDS = [3600, 86400, 259200, 604800]; // 1h, 1d, 3d, 7d

export async function enqueueDunningRetry(
  queue: Queue<DunningMessage>,
  msg: Omit<DunningMessage, 'attempt'> & { attempt?: number },
): Promise<void> {
  const attempt = msg.attempt ?? 1;
  const delaySecs = BACKOFF_SECONDS[Math.min(attempt - 1, BACKOFF_SECONDS.length - 1)];

  await queue.send(
    { ...msg, attempt },
    { delaySeconds: delaySecs },
  );
}

// src/webhooks/stripe.ts  (invoice.payment_failed branch)
export async function onPaymentFailed(
  inv: Stripe.Invoice,
  env: Env,
): Promise<void> {
  await enqueueDunningRetry(env.DUNNING_QUEUE, {
    invoiceId: inv.id,
    customerId: inv.customer as string,
    subscriptionId: inv.subscription as string,
    maxAttempts: 4,
    attempt: 1,
  });

  // Record attempt in D1
  await env.DB.prepare(
    `INSERT INTO dunning_attempts
       (invoice_id, customer_id, subscription_id, attempt, status, attempted_at)
     VALUES (?, ?, ?, 1, 'scheduled', unixepoch())`,
  )
    .bind(inv.id, inv.customer, inv.subscription)
    .run();
}
```

## Queue Consumer: Retry, Re-enqueue, or Cancel

The consumer attempts the Stripe charge. On success it reactivates the subscription and notifies the customer. On continued failure it re-enqueues with the next backoff delay or, if attempts are exhausted, cancels the subscription and triggers a final notification.

```typescript
// src/dunning/consumer.ts
import Stripe from 'stripe';

export async function dunningConsumer(
  batch: MessageBatch<DunningMessage>,
  env: Env,
): Promise<void> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  for (const message of batch.messages) {
    const { invoiceId, customerId, subscriptionId, attempt, maxAttempts } =
      message.body;

    try {
      // Attempt payment
      await stripe.invoices.pay(invoiceId, { forgive: false });

      // Success — reactivate grace period DO and record
      const id = env.GRACE_PERIOD.idFromName(subscriptionId);
      await env.GRACE_PERIOD.get(id).fetch('https://do/cancel');

      await env.DB.prepare(
        `UPDATE dunning_attempts
         SET status = 'recovered', recovered_at = unixepoch()
         WHERE invoice_id = ? AND attempt = ?`,
      )
        .bind(invoiceId, attempt)
        .run();

      await sendCustomerNotification(env, customerId, 'payment_recovered', {
        invoiceId,
      });

      message.ack();
    } catch (err: unknown) {
      const stripeErr = err as Stripe.errors.StripeError;
      const isRetriable =
        stripeErr.code === 'card_declined' ||
        stripeErr.code === 'insufficient_funds';

      if (isRetriable && attempt < maxAttempts) {
        // Re-enqueue with next backoff slot
        await enqueueDunningRetry(env.DUNNING_QUEUE, {
          invoiceId,
          customerId,
          subscriptionId,
          maxAttempts,
          attempt: attempt + 1,
        });

        await env.DB.prepare(
          `UPDATE dunning_attempts SET status = 'retrying' WHERE invoice_id = ? AND attempt = ?`,
        )
          .bind(invoiceId, attempt)
          .run();

        await sendCustomerNotification(env, customerId, 'payment_retry_pending', {
          invoiceId,
          nextAttempt: attempt + 1,
        });
      } else {
        // Exhausted — cancel subscription
        await stripe.subscriptions.cancel(subscriptionId, {
          cancellation_details: { comment: 'dunning_exhausted' },
        });

        await env.DB.prepare(
          `UPDATE dunning_attempts SET status = 'failed' WHERE invoice_id = ? AND attempt = ?`,
        )
          .bind(invoiceId, attempt)
          .run();

        await sendCustomerNotification(env, customerId, 'subscription_cancelled', {
          invoiceId,
        });
      }

      message.ack(); // always ack to prevent infinite re-delivery
    }
  }
}
```

## Grace-Period Durable Object and Dunning Analytics

A Durable Object alarm gives the subscription a hard deadline regardless of Queue timing. If no successful payment arrives before the alarm fires, the DO cancels the subscription directly. D1 dunning analytics expose recovery rates per cohort.

```typescript
// src/dunning/GracePeriodDO.ts
export class GracePeriodDO implements DurableObject {
  constructor(
    private readonly state: DurableObjectState,
    private readonly env: Env,
  ) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/start') {
      const body = await request.json<{ subscriptionId: string; graceDays: number }>();
      this.state.storage.put('subscriptionId', body.subscriptionId);
      // Set hard-deadline alarm
      const deadline = Date.now() + body.graceDays * 86_400_000;
      await this.state.storage.setAlarm(deadline);
      return new Response('started');
    }

    if (url.pathname === '/cancel') {
      await this.state.storage.deleteAlarm();
      return new Response('cancelled');
    }

    return new Response('not found', { status: 404 });
  }

  async alarm(): Promise<void> {
    const subId = await this.state.storage.get<string>('subscriptionId');
    if (!subId) return;

    const stripe = new Stripe(this.env.STRIPE_SECRET_KEY);
    await stripe.subscriptions.cancel(subId, {
      cancellation_details: { comment: 'grace_period_expired' },
    });

    await this.env.DB.prepare(
      `INSERT INTO dunning_events (subscription_id, event, created_at)
       VALUES (?, 'grace_period_expired', unixepoch())`,
    )
      .bind(subId)
      .run();
  }
}

// Analytics query — recovery rate by attempt number
// SELECT attempt,
//        COUNT(*) FILTER (WHERE status = 'recovered') * 100.0 / COUNT(*) AS recovery_pct
// FROM dunning_attempts
// GROUP BY attempt ORDER BY attempt;
```

## Anti-patterns

- Re-enqueuing on `message.retry()` instead of explicit re-enqueue with delay — the Queue's built-in retry has no per-message delay control and may fire immediately.
- Running synchronous Stripe API calls outside try/catch inside a Queue consumer — an unhandled rejection causes the entire batch to be retried, double-charging customers.
- Using a single shared cron to scan for overdue invoices instead of per-invoice Queue messages — the cron approach doesn't scale and loses per-invoice backoff state.

## Gotchas

- Cloudflare Queues `delaySeconds` maximum is 43 200 seconds (12 hours) per message as of mid-2025; for longer delays (e.g. 7-day final retry) chain multiple re-enqueues or use a Durable Object alarm as the timer instead.
- Stripe's own Smart Retries may fire concurrently with your dunning sequence; disable Stripe's automatic retries (`invoice.auto_advance = false`) on subscriptions you manage yourself to avoid duplicate charge attempts.

## Verification

```bash
# Publish a test dunning message manually
wrangler queues publish DUNNING_QUEUE \
  '{"invoiceId":"in_test","customerId":"cus_test","subscriptionId":"sub_test","attempt":1,"maxAttempts":4}'

# Check D1 dunning attempt log
wrangler d1 execute example project-db \
  --command "SELECT * FROM dunning_attempts ORDER BY attempted_at DESC LIMIT 10;"

# Tail consumer logs
wrangler tail --format=pretty
```

## Related

- `payments/payment-retry-exponential-backoff-cloudflare-queues.md`
- `payments/stripe-dunning-management.md`
- `payments/dunning-email-sequences.md`
- `payments/subscription-dunning-retry-recovery.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://stripe.com/docs/billing/subscriptions/overview#subscription-payment-behavior
- https://stripe.com/docs/invoices/automatic-collection
