# Payment Plan Installment Scheduler Workers Queues D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You need to split a purchase into fixed monthly installments (e.g., 3 × $100 for a $300 order) and charge each installment automatically on its due date, with retries for failed payments and an audit trail in D1.

## Context
Cloudflare Queues deliver scheduled charge attempts without a cron daemon. A D1 `installment_schedules` table stores each installment's due date, amount, and status. A Durable Object or a Queues consumer handles the charge, updating D1 and re-enqueueing failed attempts with exponential backoff. This pattern is PSP-agnostic — the examples use Stripe Payment Intents but the scheduler layer is the same for any gateway.

## D1 Schema

```sql
-- migrations/001_installments.sql
CREATE TABLE IF NOT EXISTS installment_plans (
  id            TEXT PRIMARY KEY,
  customer_id   TEXT NOT NULL,
  order_id      TEXT NOT NULL,
  total_cents   INTEGER NOT NULL,
  currency      TEXT NOT NULL DEFAULT 'usd',
  num_payments  INTEGER NOT NULL,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS installment_schedule (
  id            TEXT PRIMARY KEY,
  plan_id       TEXT NOT NULL REFERENCES installment_plans(id),
  sequence      INTEGER NOT NULL,        -- 1-based payment number
  amount_cents  INTEGER NOT NULL,
  due_at        INTEGER NOT NULL,        -- Unix epoch
  status        TEXT NOT NULL DEFAULT 'pending',  -- pending|processing|paid|failed|cancelled
  payment_id    TEXT,                    -- PSP charge / payment-intent ID
  attempts      INTEGER NOT NULL DEFAULT 0,
  last_error    TEXT,
  updated_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  UNIQUE(plan_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_installment_due ON installment_schedule(due_at, status);
```

## Plan Creation and Queue Seeding

When an order is created, insert the plan and every installment row, then enqueue a message for each due date. Queues does not natively support delayed delivery beyond 30 seconds — use a scheduler cron Worker to scan for due installments instead of per-message delays.

```typescript
// src/create-plan.ts
export interface Env {
  DB: D1Database;
  INSTALL_QUEUE: Queue;
  STRIPE_SECRET_KEY: string;
}

interface CreatePlanInput {
  customerId: string;
  orderId: string;
  totalCents: number;
  currency: string;
  numPayments: number;
  stripePaymentMethodId: string;
  firstDueAt?: Date;
}

export async function createInstallmentPlan(
  env: Env,
  input: CreatePlanInput
): Promise<string> {
  const planId = crypto.randomUUID();
  const firstDue = input.firstDueAt ?? new Date();
  const baseAmount = Math.floor(input.totalCents / input.numPayments);
  const remainder = input.totalCents % input.numPayments;

  const stmts: D1PreparedStatement[] = [
    env.DB.prepare(
      `INSERT INTO installment_plans
         (id, customer_id, order_id, total_cents, currency, num_payments)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(planId, input.customerId, input.orderId, input.totalCents, input.currency, input.numPayments),
  ];

  for (let seq = 1; seq <= input.numPayments; seq++) {
    const installmentId = crypto.randomUUID();
    // Add remainder to first installment
    const amountCents = seq === 1 ? baseAmount + remainder : baseAmount;
    const dueAt = new Date(firstDue);
    dueAt.setMonth(dueAt.getMonth() + (seq - 1));

    stmts.push(
      env.DB.prepare(
        `INSERT INTO installment_schedule
           (id, plan_id, sequence, amount_cents, due_at)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(installmentId, planId, seq, amountCents, Math.floor(dueAt.getTime() / 1000))
    );
  }

  await env.DB.batch(stmts);

  // Store payment method on Stripe customer for future charges
  await attachPaymentMethod(env, input.customerId, input.stripePaymentMethodId);

  return planId;
}

async function attachPaymentMethod(
  env: Env,
  stripeCustomerId: string,
  paymentMethodId: string
): Promise<void> {
  await fetch(`https://api.stripe.com/v1/payment_methods/${paymentMethodId}/attach`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: `customer=${stripeCustomerId}`,
  });
}
```

## Cron-Triggered Installment Poller

A scheduled Worker runs every minute and enqueues any installments whose `due_at` has passed and are still `pending`. The Queue consumer performs the actual charge, keeping the cron Worker lightweight.

```typescript
// src/installment-poller.ts
export async function pollDueInstallments(env: Env): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  const due = await env.DB.prepare(
    `SELECT id, plan_id, sequence, amount_cents
     FROM installment_schedule
     WHERE status = 'pending' AND due_at <= ?
     LIMIT 100`
  )
    .bind(now)
    .all<{ id: string; plan_id: string; sequence: number; amount_cents: number }>();

  if (!due.results.length) return;

  // Mark as processing before enqueuing to prevent double-dispatch
  const ids = due.results.map((r) => r.id);
  const placeholders = ids.map(() => '?').join(',');
  await env.DB.prepare(
    `UPDATE installment_schedule
     SET status = 'processing', updated_at = unixepoch()
     WHERE id IN (${placeholders})`
  )
    .bind(...ids)
    .run();

  await env.INSTALL_QUEUE.sendBatch(
    due.results.map((r) => ({ body: r, contentType: 'json' }))
  );
}
```

## Queue Consumer: Charge and Retry

```typescript
// src/installment-consumer.ts
interface InstallmentMessage {
  id: string;
  plan_id: string;
  sequence: number;
  amount_cents: number;
}

const MAX_ATTEMPTS = 4;
const BACKOFF_DAYS = [0, 1, 3, 7];

export async function processInstallment(
  env: Env,
  msg: InstallmentMessage
): Promise<void> {
  // Fetch plan details for currency and Stripe customer
  const plan = await env.DB.prepare(
    `SELECT p.currency, p.customer_id, s.attempts
     FROM installment_plans p
     JOIN installment_schedule s ON s.plan_id = p.id
     WHERE s.id = ?`
  )
    .bind(msg.id)
    .first<{ currency: string; customer_id: string; attempts: number }>();

  if (!plan) throw new Error(`Installment ${msg.id} not found`);

  const newAttempts = plan.attempts + 1;

  try {
    const pi = await chargeCustomer(
      env,
      plan.customer_id,
      msg.amount_cents,
      plan.currency,
      `Installment ${msg.sequence} of plan ${msg.plan_id}`
    );

    await env.DB.prepare(
      `UPDATE installment_schedule
       SET status = 'paid', payment_id = ?, attempts = ?, updated_at = unixepoch()
       WHERE id = ?`
    )
      .bind(pi.id, newAttempts, msg.id)
      .run();
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);

    if (newAttempts >= MAX_ATTEMPTS) {
      await env.DB.prepare(
        `UPDATE installment_schedule
         SET status = 'failed', attempts = ?, last_error = ?, updated_at = unixepoch()
         WHERE id = ?`
      )
        .bind(newAttempts, errorMsg, msg.id)
        .run();
      return; // Do not re-enqueue — trigger dunning externally
    }

    const retryDaysOffset = BACKOFF_DAYS[newAttempts] ?? 7;
    const retryDueAt = Math.floor(Date.now() / 1000) + retryDaysOffset * 86400;

    await env.DB.prepare(
      `UPDATE installment_schedule
       SET status = 'pending', attempts = ?, last_error = ?,
           due_at = ?, updated_at = unixepoch()
       WHERE id = ?`
    )
      .bind(newAttempts, errorMsg, retryDueAt, msg.id)
      .run();
  }
}

async function chargeCustomer(
  env: Env,
  stripeCustomerId: string,
  amountCents: number,
  currency: string,
  description: string
): Promise<{ id: string }> {
  const body = new URLSearchParams({
    amount: String(amountCents),
    currency,
    customer: stripeCustomerId,
    description,
    confirm: 'true',
    'payment_method_types[]': 'card',
    off_session: 'true',
  });

  const res = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  });

  if (!res.ok) {
    const err = await res.json<{ error: { message: string } }>();
    throw new Error(err.error.message);
  }

  return res.json<{ id: string }>();
}
```

## Worker Entry Point and Queue Handler

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST' && new URL(request.url).pathname === '/plans') {
      const input = await request.json<CreatePlanInput>();
      const planId = await createInstallmentPlan(env, input);
      return Response.json({ planId }, { status: 201 });
    }
    return new Response('Not Found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await pollDueInstallments(env);
  },

  async queue(batch: MessageBatch<InstallmentMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processInstallment(env, msg.body);
        msg.ack();
      } catch {
        msg.retry();
      }
    }
  },
};
```

## Anti-patterns
- Do not use Queues message delays as a timer mechanism — the maximum delay is 12 hours, insufficient for monthly installments; use a polling cron instead.
- Never charge without first marking the row `processing`; without that gate a cron re-run within the same minute will dispatch the same installment twice.
- Avoid hardcoding the split to equal amounts without rounding logic — penny gaps accumulate and cause reconciliation failures on the final installment.
- Do not cancel a plan mid-flight without voiding/refunding already-captured installments; always reconcile total collected vs. total owed.
- Never store card numbers or CVVs in D1 — always use the PSP's vault and charge by customer ID.

## Gotchas
- Stripe off-session charges require `off_session: true` and a saved payment method attached to the customer; missing either returns `authentication_required`.
- The `processing` status is a local guard only — if the Worker crashes after the DB update but before the Queue send, the row stays stuck in `processing`. Add a recovery query that resets rows stuck in `processing` for more than 5 minutes back to `pending`.
- D1 `batch()` is not a true transaction; if the `installment_plans` insert succeeds but a subsequent `installment_schedule` insert fails, you'll have an orphan plan row.
- Queue messages have a visibility timeout — if `processInstallment` takes longer than the timeout, the message is redelivered. Keep the charge function under 25 seconds.
- Proration for mid-cycle plan changes (e.g., upgrading from 3 to 6 installments) requires cancelling all `pending` rows and inserting a new plan; never mutate existing schedules in place.

## Verification
1. Create a plan via `POST /plans` with `numPayments=3`, `totalCents=30001` (odd cents test), and a Stripe test customer.
2. Confirm 3 rows in `installment_schedule` with correct `amount_cents` (10001, 10000, 10000).
3. Manually set `due_at` to now minus 60 seconds on one row and trigger the cron; confirm it moves to `processing` then `paid`.
4. Simulate a Stripe charge failure (use test card `4000 0000 0000 0341`) and confirm the row is rescheduled with incremented `attempts`.
5. Exhaust `MAX_ATTEMPTS` and confirm the row reaches `failed` status.

## Related
- `payment-retry-exponential-backoff-cloudflare-queues.md`
- `payment-dunning-management-cloudflare-queues.md`
- `stripe-subscription-pause-resume.md`
- `stripe-per-seat-quantity-billing.md`
- `stripe-metered-billing.md`

## Sources
- https://developers.cloudflare.com/queues/
- https://stripe.com/docs/payments/payment-intents/off-session
- https://developers.cloudflare.com/d1/
