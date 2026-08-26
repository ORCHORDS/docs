# Compensating Transaction Pattern for Failed Multi-Step Payment Flows

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A payment checkout involves several sequential steps: create an order in D1, charge a payment method via Stripe, send a confirmation email, and provision the purchased resource (e.g., activate a subscription). If step 3 or 4 fails, the order row exists and the charge has been captured — but the user has no subscription. Retrying the whole flow double-charges. Rolling back only in memory is lost on a Worker crash. You need a way to undo the work already done in a reliable, auditable manner when a later step fails.

## Context

In distributed systems, ACID transactions are unavailable across service boundaries (D1 ↔ Stripe ↔ Email ↔ Resource API). The **Compensating Transaction** pattern models each forward operation with a paired undo operation. If the forward sequence fails at step N, the system executes compensations for steps N-1 down to 1 in reverse order.

This pattern is a building block of the **Saga** pattern (see `saga-pattern-multi-step-workers.md`). The present article focuses specifically on payment flows where partial execution leaves real money and real resources in inconsistent states.

```
  Forward operations:
  ─────────────────────────────────────────────────────────────────►
  [1] INSERT order   [2] Stripe charge  [3] Send email  [4] Activate sub
                                                              ▼ FAILS
  Compensating operations (in reverse):
  ◄─────────────────────────────────────────────────────────────────
                      [C2] Stripe refund  [C1] Mark order CANCELLED
  (email was sent — no compensation needed; resource not activated — nothing to undo)
```

Key constraint: **compensations must be idempotent** — if a compensation itself is retried it must produce the same result.

## Section 1 — Data Model for Compensation State

Store compensation state in D1 so it survives Worker crashes:

```sql
-- migrations/0001_payment_sagas.sql

CREATE TABLE IF NOT EXISTS payment_sagas (
  saga_id          TEXT    PRIMARY KEY,
  status           TEXT    NOT NULL DEFAULT 'PENDING',
    -- PENDING | RUNNING | COMPLETED | COMPENSATING | COMPENSATED | FAILED
  current_step     INTEGER NOT NULL DEFAULT 0,
  steps_completed  TEXT    NOT NULL DEFAULT '[]',   -- JSON array of step names
  context_json     TEXT    NOT NULL DEFAULT '{}',   -- accumulated step outputs
  failure_reason   TEXT,
  created_at       TEXT    NOT NULL,
  updated_at       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_saga_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  saga_id     TEXT    NOT NULL REFERENCES payment_sagas(saga_id),
  event_type  TEXT    NOT NULL,   -- STEP_STARTED | STEP_COMPLETED | STEP_COMPENSATED | etc.
  step_name   TEXT,
  detail_json TEXT,
  created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saga_events_saga_id ON payment_saga_events (saga_id);
```

## Section 2 — Saga Step Interface

```typescript
// saga-types.ts

export interface PaymentContext {
  orderId?:       string;
  stripeChargeId?: string;
  emailSent?:     boolean;
  subscriptionId?: string;
}

export interface SagaStep<TCtx> {
  name:       string;
  execute:    (ctx: TCtx, env: Env) => Promise<Partial<TCtx>>;
  compensate: (ctx: TCtx, env: Env) => Promise<void>;
}

export interface Env {
  DB:            D1Database;
  STRIPE_SECRET: string;
  RESEND_KEY:    string;
}
```

## Section 3 — Step Implementations

```typescript
// steps/create-order.ts
import type { SagaStep, PaymentContext, Env } from '../saga-types';

export const createOrderStep: SagaStep<PaymentContext> = {
  name: 'create_order',

  async execute(ctx, env) {
    const orderId = crypto.randomUUID();
    await env.DB
      .prepare(`INSERT INTO orders (id, user_id, status, created_at)
                VALUES (?, ?, 'PENDING', ?)`)
      .bind(orderId, ctx.userId, new Date().toISOString())
      .run();
    return { orderId };
  },

  async compensate(ctx, env) {
    if (!ctx.orderId) return; // Nothing to undo
    await env.DB
      .prepare(`UPDATE orders SET status = 'CANCELLED', cancelled_at = ? WHERE id = ?`)
      .bind(new Date().toISOString(), ctx.orderId)
      .run();
  },
};
```

```typescript
// steps/stripe-charge.ts
import type { SagaStep, PaymentContext, Env } from '../saga-types';

export const stripeChargeStep: SagaStep<PaymentContext> = {
  name: 'stripe_charge',

  async execute(ctx, env) {
    const res = await fetch('https://api.stripe.com/v1/charges', {
      method:  'POST',
      headers: {
        'Authorization': `Bearer ${env.STRIPE_SECRET}`,
        'Content-Type':  'application/x-www-form-urlencoded',
        // Idempotency key prevents double-charge on retry
        'Idempotency-Key': `charge-${ctx.orderId}`,
      },
      body: new URLSearchParams({
        amount:   String(ctx.amountCents),
        currency: ctx.currency ?? 'usd',
        source:   ctx.stripeToken!,
      }),
    });

    if (!res.ok) {
      const err = await res.json<{ error: { message: string } }>();
      throw new Error(`Stripe charge failed: ${err.error.message}`);
    }

    const charge = await res.json<{ id: string }>();
    return { stripeChargeId: charge.id };
  },

  async compensate(ctx, env) {
    if (!ctx.stripeChargeId) return;

    const res = await fetch(`https://api.stripe.com/v1/refunds`, {
      method:  'POST',
      headers: {
        'Authorization':  `Bearer ${env.STRIPE_SECRET}`,
        'Content-Type':   'application/x-www-form-urlencoded',
        'Idempotency-Key': `refund-${ctx.orderId}`, // idempotent refund
      },
      body: new URLSearchParams({ charge: ctx.stripeChargeId }),
    });

    if (!res.ok && res.status !== 400) {
      // 400 can mean already refunded — treat as success
      throw new Error(`Stripe refund failed: ${res.status}`);
    }
  },
};
```

```typescript
// steps/activate-subscription.ts
import type { SagaStep, PaymentContext, Env } from '../saga-types';

export const activateSubscriptionStep: SagaStep<PaymentContext> = {
  name: 'activate_subscription',

  async execute(ctx, env) {
    const subId = crypto.randomUUID();
    await env.DB
      .prepare(`INSERT INTO subscriptions (id, user_id, order_id, plan_id, status, created_at)
                VALUES (?, ?, ?, ?, 'ACTIVE', ?)`)
      .bind(subId, ctx.userId, ctx.orderId, ctx.planId, new Date().toISOString())
      .run();
    return { subscriptionId: subId };
  },

  async compensate(ctx, env) {
    if (!ctx.subscriptionId) return;
    await env.DB
      .prepare(`UPDATE subscriptions SET status = 'CANCELLED', cancelled_at = ? WHERE id = ?`)
      .bind(new Date().toISOString(), ctx.subscriptionId)
      .run();
  },
};
```

## Section 4 — Saga Orchestrator

```typescript
// saga-orchestrator.ts
import type { SagaStep, PaymentContext, Env } from './saga-types';
import { createOrderStep }          from './steps/create-order';
import { stripeChargeStep }         from './steps/stripe-charge';
import { activateSubscriptionStep } from './steps/activate-subscription';

const STEPS: SagaStep<PaymentContext>[] = [
  createOrderStep,
  stripeChargeStep,
  activateSubscriptionStep,
];

export async function runPaymentSaga(
  initialCtx: PaymentContext,
  env:         Env,
): Promise<PaymentContext> {
  const sagaId    = crypto.randomUUID();
  const now       = new Date().toISOString();
  let ctx: PaymentContext = { ...initialCtx };

  // Create saga record
  await env.DB
    .prepare(`INSERT INTO payment_sagas (saga_id, status, current_step, steps_completed, context_json, created_at, updated_at)
              VALUES (?, 'RUNNING', 0, '[]', ?, ?, ?)`)
    .bind(sagaId, JSON.stringify(ctx), now, now)
    .run();

  let completedUpTo = -1;

  // Forward phase
  for (let i = 0; i < STEPS.length; i++) {
    const step = STEPS[i];
    try {
      await logSagaEvent(env.DB, sagaId, 'STEP_STARTED', step.name);

      const patch = await step.execute(ctx, env);
      ctx = { ...ctx, ...patch };
      completedUpTo = i;

      await env.DB
        .prepare(`UPDATE payment_sagas SET current_step = ?, context_json = ?, updated_at = ? WHERE saga_id = ?`)
        .bind(i + 1, JSON.stringify(ctx), new Date().toISOString(), sagaId)
        .run();

      await logSagaEvent(env.DB, sagaId, 'STEP_COMPLETED', step.name, patch);
    } catch (err) {
      const reason = String(err);
      console.error(JSON.stringify({ event: 'saga_step_failed', sagaId, step: step.name, reason }));

      await env.DB
        .prepare(`UPDATE payment_sagas SET status = 'COMPENSATING', failure_reason = ?, updated_at = ? WHERE saga_id = ?`)
        .bind(reason, new Date().toISOString(), sagaId)
        .run();

      await compensate(sagaId, ctx, completedUpTo, env);
      throw new SagaError(sagaId, step.name, reason);
    }
  }

  // All steps succeeded
  await env.DB
    .prepare(`UPDATE payment_sagas SET status = 'COMPLETED', updated_at = ? WHERE saga_id = ?`)
    .bind(new Date().toISOString(), sagaId)
    .run();

  return ctx;
}

async function compensate(
  sagaId:       string,
  ctx:          PaymentContext,
  upToIndex:    number,
  env:          Env,
): Promise<void> {
  // Compensate in reverse order
  for (let i = upToIndex; i >= 0; i--) {
    const step = STEPS[i];
    try {
      await logSagaEvent(env.DB, sagaId, 'COMPENSATION_STARTED', step.name);
      await step.compensate(ctx, env);
      await logSagaEvent(env.DB, sagaId, 'COMPENSATION_COMPLETED', step.name);
    } catch (err) {
      // Log but continue compensating remaining steps
      console.error(JSON.stringify({ event: 'compensation_failed', sagaId, step: step.name, error: String(err) }));
      await logSagaEvent(env.DB, sagaId, 'COMPENSATION_FAILED', step.name, { error: String(err) });
    }
  }

  await env.DB
    .prepare(`UPDATE payment_sagas SET status = 'COMPENSATED', updated_at = ? WHERE saga_id = ?`)
    .bind(new Date().toISOString(), sagaId)
    .run();
}

async function logSagaEvent(
  db:     D1Database,
  sagaId: string,
  type:   string,
  step:   string,
  detail?: unknown,
): Promise<void> {
  await db
    .prepare(`INSERT INTO payment_saga_events (saga_id, event_type, step_name, detail_json, created_at)
              VALUES (?, ?, ?, ?, ?)`)
    .bind(sagaId, type, step, detail ? JSON.stringify(detail) : null, new Date().toISOString())
    .run();
}

export class SagaError extends Error {
  constructor(
    public readonly sagaId:   string,
    public readonly failedAt: string,
    public readonly reason:   string,
  ) {
    super(`Saga ${sagaId} failed at step "${failedAt}": ${reason}`);
    this.name = 'SagaError';
  }
}
```

## Anti-patterns

**Compensations that are not idempotent.** Calling `stripe.refunds.create({ charge })` twice creates a second refund error or a double refund. Always use an `Idempotency-Key` derived from stable IDs so re-running the compensation is safe.

**Ignoring compensation failures.** If a compensation itself throws and is swallowed, the system is in a partially compensated state with no record. Always log compensation failures at ERROR level and surface them in an alert, even if you continue compensating other steps.

**Compensating in forward order.** `create_order` then `stripe_charge` must be compensated as `refund` then `cancel_order` — reverse order prevents referential integrity issues where a D1 row has a FK to the charge.

**Using in-memory state for the saga context.** If the Worker crashes between steps, the context is lost and the saga cannot be resumed or compensated. Always persist `context_json` to D1 after each successful step.

**Running compensation inside a D1 transaction.** Compensations span multiple services (Stripe, email, D1). D1 transactions are local; wrapping a Stripe API call inside one does nothing. Compensations must be at-least-once with idempotency, not atomic.

## Gotchas

- **Stripe `Idempotency-Key` expires after 24 hours.** If a compensation is retried more than 24 hours after the original charge, generate a new idempotency key derived from `refund-${orderId}-${dayOfYear}` to handle this edge case.
- **Email sends cannot be compensated.** Once sent, an email is delivered. Design step ordering so irreversible steps (email, SMS) come last; compensations should not need to undo them.
- **D1 write-after-crash recovery.** On Worker restart, a saga in `RUNNING` or `COMPENSATING` state in D1 needs a recovery job (cron or Queue-triggered) to detect stuck sagas older than 5 minutes and resume or complete compensation.
- **`ctx` is accumulated across steps.** Pass `ctx` by value (spread) to each step to avoid mutation surprises when compensating with an older context snapshot.

## Verification

```bash
# Happy path
curl -X POST https://api.example.com/checkout \
  -H "Content-Type: application/json" \
  -d '{"userId":"u1","planId":"pro","stripeToken":"tok_visa","amountCents":4900,"currency":"usd"}'

# Check saga record
wrangler d1 execute my-db --command \
  "SELECT saga_id, status, current_step FROM payment_sagas ORDER BY created_at DESC LIMIT 1;"

# Simulate step-3 failure (e.g., set DB to reject inserts) and verify compensation
wrangler d1 execute my-db --command \
  "SELECT event_type, step_name FROM payment_saga_events ORDER BY id DESC LIMIT 10;"
```

## Related

- `saga-pattern-multi-step-workers.md` — broader saga orchestration in Workers
- `saga-pattern.md` — conceptual overview of sagas vs. two-phase commit
- `idempotency-key-pattern-workers-d1.md` — idempotent operations in Workers
- `retry-with-exponential-backoff.md` — retry strategy for transient step failures
- `database-transaction-design.md` — local D1 transaction boundaries

## Sources

- Hector Garcia-Molina & Kenneth Salem, "Sagas" (1987) — ACM SIGMOD
- Chris Richardson, "Microservices Patterns" — Chapter 4: Managing Transactions with Sagas
- Stripe Idempotency Keys — stripe.com/docs/api/idempotent_requests
- Cloudflare D1 documentation — developers.cloudflare.com/d1/
