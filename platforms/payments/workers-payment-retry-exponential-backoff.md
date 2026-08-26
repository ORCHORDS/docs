# Payment Retry with Exponential Backoff in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A payment charge fails with a transient network error or a soft card decline. Retrying immediately often succeeds, but hammering the processor without a delay damages your relationship with both the issuer and Stripe. You need a retry pipeline that respects backoff intervals, distinguishes permanent failures (stolen card) from transient ones (network timeout), parks definitively failed payments in a dead-letter queue, and notifies the customer only after all retry attempts are exhausted.

## Context

Cloudflare Queues provides at-least-once delivery with configurable retry and delay settings. Each queue message can carry arbitrary JSON. The retry pipeline consists of two queues:

1. **`payment-retry`** — receives initial payment jobs and re-queued retries with backoff metadata.
2. **`payment-dlq`** — receives messages that have exceeded `MAX_RETRIES`.

The Worker acts as both producer (when a checkout flow initiates a charge) and consumer (when Queues delivers a retry message). Stripe error codes drive the retryable/non-retryable classification.

## Solution

```typescript
import Stripe from 'stripe';
import { Env } from './types';

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1_000; // 1 second
const MAX_DELAY_MS = 60_000 * 30; // 30 minutes cap

// ── Error classification ──────────────────────────────────────────────────────

/**
 * Non-retryable Stripe decline codes — permanent card/account issues.
 * Full list: https://stripe.com/docs/declines/codes
 */
const NON_RETRYABLE_CODES = new Set([
  'card_declined',
  'expired_card',
  'incorrect_cvc',
  'incorrect_number',
  'insufficient_funds',
  'do_not_honor',
  'do_not_try_again',
  'fraudulent',
  'lost_card',
  'stolen_card',
  'pickup_card',
  'restricted_card',
  'revocation_of_authorization',
]);

function isRetryable(err: unknown): boolean {
  if (err instanceof Stripe.errors.StripeCardError) {
    const code = err.code ?? '';
    return !NON_RETRYABLE_CODES.has(code);
  }
  // Network errors, rate limits, and Stripe 5xx are retryable.
  if (err instanceof Stripe.errors.StripeConnectionError) return true;
  if (err instanceof Stripe.errors.StripeAPIError) return true;
  if (err instanceof Stripe.errors.StripeRateLimitError) return true;
  return false;
}

// ── Backoff calculation ───────────────────────────────────────────────────────

/**
 * Full jitter exponential backoff.
 * delay = random(0, min(cap, base * 2^attempt))
 * Reference: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
 */
function calcBackoffMs(attempt: number): number {
  const exponential = BASE_DELAY_MS * Math.pow(2, attempt);
  const capped = Math.min(exponential, MAX_DELAY_MS);
  return Math.floor(Math.random() * capped);
}

// ── Queue message types ───────────────────────────────────────────────────────

type PaymentJob = {
  jobId: string; // idempotency key for Stripe
  customerId: string;
  amount: number; // in cents
  currency: string;
  paymentMethodId: string;
  attempt: number; // 0-indexed
  scheduledAt: number; // Unix ms — when this attempt should run
  originalJobId: string; // for DLQ correlation
};

type DlqRecord = PaymentJob & {
  finalError: string;
  failedAt: number;
};

// ── Stripe charge attempt ─────────────────────────────────────────────────────

async function chargePaymentMethod(
  stripe: Stripe,
  job: PaymentJob,
): Promise<Stripe.PaymentIntent> {
  return stripe.paymentIntents.create(
    {
      amount: job.amount,
      currency: job.currency,
      customer: job.customerId,
      payment_method: job.paymentMethodId,
      confirm: true,
      off_session: true,
      error_on_requires_action: true,
    },
    {
      idempotencyKey: `pi-${job.jobId}-attempt-${job.attempt}`,
    },
  );
}

// ── Notification helper ───────────────────────────────────────────────────────

async function notifyCustomerFinalFailure(
  env: Env,
  job: PaymentJob,
  reason: string,
): Promise<void> {
  // Push a notification job to a separate notifications queue.
  await env.NOTIFICATION_QUEUE.send({
    type: 'payment_failed_final',
    customerId: job.customerId,
    amount: job.amount,
    currency: job.currency,
    reason,
    jobId: job.originalJobId,
  });
}

// ── D1 audit log ─────────────────────────────────────────────────────────────

async function recordAttempt(
  db: D1Database,
  job: PaymentJob,
  outcome: 'succeeded' | 'retrying' | 'failed_permanent' | 'dlq',
  errorMessage?: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO payment_attempts
         (job_id, original_job_id, customer_id, attempt, outcome, error_message, attempted_at)
       VALUES (?, ?, ?, ?, ?, ?, unixepoch())`,
    )
    .bind(
      job.jobId,
      job.originalJobId,
      job.customerId,
      job.attempt,
      outcome,
      errorMessage ?? null,
    )
    .run();
}

// ── Queue consumer ────────────────────────────────────────────────────────────

export default {
  // Called by the checkout API to enqueue the first payment attempt.
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.json<{
      customerId: string;
      amount: number;
      currency: string;
      paymentMethodId: string;
    }>();

    const jobId = crypto.randomUUID();
    const job: PaymentJob = {
      jobId,
      customerId: body.customerId,
      amount: body.amount,
      currency: body.currency,
      paymentMethodId: body.paymentMethodId,
      attempt: 0,
      scheduledAt: Date.now(),
      originalJobId: jobId,
    };

    await env.PAYMENT_RETRY_QUEUE.send(job);
    return Response.json({ jobId }, { status: 202 });
  },

  // Cloudflare Queues batch consumer.
  async queue(batch: MessageBatch<PaymentJob>, env: Env): Promise<void> {
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

    for (const message of batch.messages) {
      const job = message.body;

      // Honour scheduled delay: if the message arrived early, re-send with
      // the remaining delay. (Queues supports delivery delay up to 12 hours.)
      const waitMs = job.scheduledAt - Date.now();
      if (waitMs > 1_000) {
        const delaySec = Math.min(Math.ceil(waitMs / 1_000), 43_200);
        await env.PAYMENT_RETRY_QUEUE.send(job, { delaySeconds: delaySec });
        message.ack();
        continue;
      }

      try {
        const pi = await chargePaymentMethod(stripe, job);
        console.log(`[retry] Payment succeeded: ${pi.id} (job ${job.jobId}, attempt ${job.attempt})`);
        await recordAttempt(env.DB, job, 'succeeded');
        message.ack();
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error(`[retry] Attempt ${job.attempt} failed for job ${job.jobId}: ${errorMsg}`);

        if (!isRetryable(err) || job.attempt >= MAX_RETRIES) {
          // Permanent failure — send to DLQ and notify customer.
          const dlqRecord: DlqRecord = {
            ...job,
            finalError: errorMsg,
            failedAt: Date.now(),
          };
          await env.PAYMENT_DLQ.send(dlqRecord);
          await recordAttempt(env.DB, job, 'dlq', errorMsg);
          await notifyCustomerFinalFailure(env, job, errorMsg);
          message.ack();
        } else {
          // Retryable — schedule next attempt with backoff.
          const backoffMs = calcBackoffMs(job.attempt + 1);
          const nextJob: PaymentJob = {
            ...job,
            attempt: job.attempt + 1,
            scheduledAt: Date.now() + backoffMs,
            jobId: crypto.randomUUID(), // new idempotency key per attempt
          };
          const delaySec = Math.min(Math.ceil(backoffMs / 1_000), 43_200);
          await env.PAYMENT_RETRY_QUEUE.send(nextJob, { delaySeconds: delaySec });
          await recordAttempt(env.DB, job, 'retrying', errorMsg);
          message.ack();
        }
      }
    }
  },
};
```

## Implementation Details

**D1 schema:**

```sql
CREATE TABLE payment_attempts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id          TEXT NOT NULL,
  original_job_id TEXT NOT NULL,
  customer_id     TEXT NOT NULL,
  attempt         INTEGER NOT NULL,
  outcome         TEXT NOT NULL CHECK(outcome IN ('succeeded','retrying','failed_permanent','dlq')),
  error_message   TEXT,
  attempted_at    INTEGER NOT NULL
);

CREATE INDEX idx_payment_attempts_original ON payment_attempts(original_job_id);
```

**`wrangler.toml`:**

```toml
[[queues.producers]]
binding = "PAYMENT_RETRY_QUEUE"
queue   = "payment-retry"

[[queues.producers]]
binding = "PAYMENT_DLQ"
queue   = "payment-dlq"

[[queues.producers]]
binding = "NOTIFICATION_QUEUE"
queue   = "notifications"

[[queues.consumers]]
queue            = "payment-retry"
max_batch_size   = 10
max_batch_timeout = 5
max_retries      = 0     # We manage retries ourselves
dead_letter_queue = "payment-dlq"
```

**Backoff schedule (BASE=1s, cap=30min):**

| Attempt | Max window | Example delay |
|---------|-----------|---------------|
| 1       | 2 s       | ~1.4 s        |
| 2       | 4 s       | ~2.8 s        |
| 3       | 8 s       | ~5.6 s        |
| 4       | 16 s      | ~11 s         |
| 5       | 32 s      | ~22 s         |

With `MAX_RETRIES = 5` the pipeline makes 6 total attempts before parking in the DLQ.

## Anti-patterns

- **Retrying synchronously inside the Worker.** A Worker has a 30-second CPU time limit. Sleeping for backoff inside the handler wastes the connection and risks timeout. Always re-enqueue via Queues.
- **Sharing a single idempotency key across retries.** If attempt 1 partially succeeded (charge created, response lost), reusing the same key would return the original error. Create a new idempotency key per attempt.
- **Notifying the customer on every failure.** Only send the final-failure email after all retries are exhausted. Intermediate failures are internal.
- **Treating `insufficient_funds` as retryable.** The card has no funds right now; retrying seconds later will not help. It belongs in `NON_RETRYABLE_CODES`.

## Gotchas

- Queues `delaySeconds` maximum is 43,200 (12 hours). For longer backoff windows (30-minute cap as here), re-queue the message and let it arrive early; the consumer checks `scheduledAt` and re-sends with the remaining delay if it arrives too soon.
- `message.ack()` must be called for every message in the batch, even on error paths. If you omit it, Queues retries the message using its own retry mechanism, bypassing your custom backoff.
- Stripe's `off_session: true` flag tells the API to attempt without 3DS. Set `error_on_requires_action: true` so the PaymentIntent fails immediately rather than entering `requires_action` indefinitely.

## Verification

```bash
# Trigger a test job via the fetch handler:
curl -X POST https://your-worker.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"cus_test","amount":1000,"currency":"usd","paymentMethodId":"pm_card_chargeDeclined"}'

# Watch attempt log:
wrangler d1 execute payments --command \
  "SELECT original_job_id, attempt, outcome, error_message FROM payment_attempts ORDER BY attempted_at;"

# Inspect DLQ:
wrangler queues consumer messages payment-dlq
```

## Related

- `documentation/categories/payments/workers-stripe-webhook-idempotency.md`
- `documentation/categories/payments/workers-subscription-lifecycle-manager.md`
- `documentation/categories/payments/workers-refund-automation-pipeline.md`

## Sources

- AWS Jitter Blog: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Stripe Decline Codes: https://stripe.com/docs/declines/codes
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Stripe off-session payments: https://stripe.com/docs/payments/save-and-reuse?platform=web#charge-saved-payment-method
