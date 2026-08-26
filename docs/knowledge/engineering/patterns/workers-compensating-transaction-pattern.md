# Compensating Transactions for Distributed Rollback

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A multi-step business process spans several external services (payment gateway, inventory service, shipping service). One step fails halfway through. You cannot use a database `ROLLBACK` because some steps have already made network calls with side effects. You need a **saga** that tracks which steps succeeded and automatically executes their compensation actions in reverse order.

---

## Context

The [Saga pattern](https://microservices.io/patterns/data/saga.html) models a distributed transaction as a sequence of local transactions. Each step has a **forward action** and a **compensation action** (its logical inverse). If step N fails, the saga runs compensations for steps N-1 down to 1 in reverse order.

A **choreography-based saga** has no central coordinator — services react to events. An **orchestration-based saga** uses a coordinator that drives each step. Here we implement an orchestration-based saga using a Durable Object as the coordinator, with saga history persisted in D1 for durability and auditability.

---

## Solution

```typescript
// src/types.ts
export interface Env {
  SAGA_COORDINATOR: DurableObjectNamespace;
  DB: D1Database;
  PAYMENT_SERVICE_URL: string;
  INVENTORY_SERVICE_URL: string;
  SHIPPING_SERVICE_URL: string;
}

export type StepStatus = 'pending' | 'completed' | 'compensating' | 'compensated' | 'failed';

export interface SagaStep {
  name: string;
  status: StepStatus;
  completedAt?: string;
  compensatedAt?: string;
  error?: string;
  retries: number;
}

export interface SagaState {
  sagaId: string;
  orderId: string;
  steps: SagaStep[];
  status: 'running' | 'completed' | 'compensating' | 'failed';
  startedAt: string;
  finishedAt?: string;
}

export interface OrderPayload {
  orderId: string;
  userId: string;
  amount: number;
  currency: string;
  items: { sku: string; qty: number }[];
  shippingAddress: string;
}

// src/saga-coordinator-do.ts
import { DurableObject } from 'cloudflare:workers';
import { Env, SagaState, SagaStep, StepStatus, OrderPayload } from './types';

const MAX_COMPENSATION_RETRIES = 3;
const COMPENSATION_TIMEOUT_MS = 10_000;

export class SagaCoordinatorDO extends DurableObject {
  constructor(ctx: DurableObjectState, private env: Env) {
    super(ctx, env);
  }

  async fetch(request: Request): Promise<Response> {
    const { method, payload } = await request.json<{ method: string; payload: OrderPayload }>();

    if (method === 'start') {
      const result = await this.runSaga(payload);
      return Response.json(result);
    }

    return new Response('Unknown method', { status: 400 });
  }

  private async runSaga(order: OrderPayload): Promise<SagaState> {
    const sagaId = crypto.randomUUID();
    const now = new Date().toISOString();

    const state: SagaState = {
      sagaId,
      orderId: order.orderId,
      status: 'running',
      startedAt: now,
      steps: [
        { name: 'chargePayment', status: 'pending', retries: 0 },
        { name: 'reserveInventory', status: 'pending', retries: 0 },
        { name: 'scheduleShipment', status: 'pending', retries: 0 },
      ],
    };

    await this.persistState(state);

    const stepHandlers: Record<string, () => Promise<void>> = {
      chargePayment: () => this.chargePayment(order),
      reserveInventory: () => this.reserveInventory(order),
      scheduleShipment: () => this.scheduleShipment(order),
    };

    const compensationHandlers: Record<string, () => Promise<void>> = {
      chargePayment: () => this.refundPayment(order),
      reserveInventory: () => this.releaseInventory(order),
      scheduleShipment: () => this.cancelShipment(order),
    };

    let failedAt = -1;

    for (let i = 0; i < state.steps.length; i++) {
      const step = state.steps[i];
      try {
        console.log(JSON.stringify({ event: 'saga_step_start', sagaId, step: step.name }));
        await stepHandlers[step.name]();
        step.status = 'completed';
        step.completedAt = new Date().toISOString();
        await this.persistState(state);
        console.log(JSON.stringify({ event: 'saga_step_done', sagaId, step: step.name }));
      } catch (err) {
        step.status = 'failed';
        step.error = String(err);
        await this.persistState(state);
        failedAt = i;
        console.error(JSON.stringify({ event: 'saga_step_failed', sagaId, step: step.name, error: String(err) }));
        break;
      }
    }

    if (failedAt >= 0) {
      state.status = 'compensating';
      await this.persistState(state);

      // Compensate completed steps in reverse order
      for (let i = failedAt - 1; i >= 0; i--) {
        const step = state.steps[i];
        step.status = 'compensating';
        await this.persistState(state);

        const compensated = await this.executeCompensation(
          sagaId,
          step,
          compensationHandlers[step.name],
        );

        if (!compensated) {
          state.status = 'failed';
          await this.persistState(state);
          console.error(JSON.stringify({ event: 'saga_compensation_failed', sagaId, step: step.name }));
          return state;
        }
      }

      state.status = 'failed';
      state.finishedAt = new Date().toISOString();
      await this.persistState(state);
    } else {
      state.status = 'completed';
      state.finishedAt = new Date().toISOString();
      await this.persistState(state);
      console.log(JSON.stringify({ event: 'saga_completed', sagaId }));
    }

    return state;
  }

  /**
   * Execute a compensation action with retries and timeout.
   * Returns true if compensation succeeded, false if it exhausted retries.
   */
  private async executeCompensation(
    sagaId: string,
    step: SagaStep,
    handler: () => Promise<void>,
  ): Promise<boolean> {
    while (step.retries <= MAX_COMPENSATION_RETRIES) {
      try {
        // Race compensation against a timeout
        await Promise.race([
          handler(),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('compensation_timeout')), COMPENSATION_TIMEOUT_MS)
          ),
        ]);
        step.status = 'compensated';
        step.compensatedAt = new Date().toISOString();
        console.log(JSON.stringify({ event: 'saga_compensated', sagaId, step: step.name }));
        return true;
      } catch (err) {
        step.retries += 1;
        step.error = String(err);
        console.error(JSON.stringify({
          event: 'saga_compensation_retry',
          sagaId,
          step: step.name,
          retries: step.retries,
          error: String(err),
        }));
        if (step.retries > MAX_COMPENSATION_RETRIES) return false;
        // Exponential backoff between retries (1 s, 2 s, 4 s)
        await new Promise((r) => setTimeout(r, 1000 * 2 ** (step.retries - 1)));
      }
    }
    return false;
  }

  private async persistState(state: SagaState): Promise<void> {
    // Persist to Durable Object storage for in-flight resilience
    await this.ctx.storage.put('state', state);

    // Also write to D1 for auditability and cross-saga queries
    await this.env.DB.prepare(`
      INSERT INTO saga_history (saga_id, order_id, status, steps, started_at, finished_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(saga_id) DO UPDATE SET
        status = excluded.status,
        steps = excluded.steps,
        finished_at = excluded.finished_at,
        updated_at = excluded.updated_at
    `).bind(
      state.sagaId,
      state.orderId,
      state.status,
      JSON.stringify(state.steps),
      state.startedAt,
      state.finishedAt ?? null,
      new Date().toISOString(),
    ).run();
  }

  // --- Step implementations (idempotent by design) ---

  private async chargePayment(order: OrderPayload): Promise<void> {
    const r = await fetch(`${this.env.PAYMENT_SERVICE_URL}/charge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': order.orderId },
      body: JSON.stringify({ orderId: order.orderId, amount: order.amount, currency: order.currency }),
    });
    if (!r.ok) throw new Error(`chargePayment failed: ${r.status}`);
  }

  private async refundPayment(order: OrderPayload): Promise<void> {
    const r = await fetch(`${this.env.PAYMENT_SERVICE_URL}/refund`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `refund-${order.orderId}` },
      body: JSON.stringify({ orderId: order.orderId }),
    });
    if (!r.ok) throw new Error(`refundPayment failed: ${r.status}`);
  }

  private async reserveInventory(order: OrderPayload): Promise<void> {
    const r = await fetch(`${this.env.INVENTORY_SERVICE_URL}/reserve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': order.orderId },
      body: JSON.stringify({ orderId: order.orderId, items: order.items }),
    });
    if (!r.ok) throw new Error(`reserveInventory failed: ${r.status}`);
  }

  private async releaseInventory(order: OrderPayload): Promise<void> {
    const r = await fetch(`${this.env.INVENTORY_SERVICE_URL}/release`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `release-${order.orderId}` },
      body: JSON.stringify({ orderId: order.orderId, items: order.items }),
    });
    if (!r.ok) throw new Error(`releaseInventory failed: ${r.status}`);
  }

  private async scheduleShipment(order: OrderPayload): Promise<void> {
    const r = await fetch(`${this.env.SHIPPING_SERVICE_URL}/schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': order.orderId },
      body: JSON.stringify({ orderId: order.orderId, address: order.shippingAddress }),
    });
    if (!r.ok) throw new Error(`scheduleShipment failed: ${r.status}`);
  }

  private async cancelShipment(order: OrderPayload): Promise<void> {
    const r = await fetch(`${this.env.SHIPPING_SERVICE_URL}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `cancel-${order.orderId}` },
      body: JSON.stringify({ orderId: order.orderId }),
    });
    if (!r.ok) throw new Error(`cancelShipment failed: ${r.status}`);
  }
}

// src/worker.ts — entry point
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/orders') {
      return new Response('Not found', { status: 404 });
    }
    const order = await request.json<OrderPayload>();
    const doId = env.SAGA_COORDINATOR.idFromName(order.orderId);
    const stub = env.SAGA_COORDINATOR.get(doId);
    const result = await stub.fetch(new Request('https://do/', {
      method: 'POST',
      body: JSON.stringify({ method: 'start', payload: order }),
    }));
    return result;
  },
};
```

---

## Implementation Details

**DO as saga coordinator:** Each saga instance maps to one DO instance (`idFromName(orderId)`). The DO holds in-flight state in `ctx.storage` and writes a durable record to D1. If the DO is evicted mid-saga (rare), the next request rehydrates from storage and can resume or be replayed.

**Idempotent forward and compensation actions:** Each service call includes an `Idempotency-Key` header derived from `orderId` (with a prefix for compensations, e.g. `refund-{orderId}`). This ensures that retrying a step after a network error does not double-charge or double-refund.

**Compensation timeout:** Each compensation is raced against a 10-second timeout using `Promise.race`. This prevents a hanging external service from blocking the entire saga. After timeout, the step is retried up to `MAX_COMPENSATION_RETRIES` times with exponential backoff.

**D1 saga history:** The `saga_history` table stores the full step trace with timestamps and error messages. Use this for support investigations, SLA reporting, and replaying sagas whose compensation failed.

---

## Anti-patterns

- **Non-idempotent forward actions.** If `chargePayment` charges on every call without deduplication, a retry after a network timeout causes a double charge. Always pass an idempotency key.
- **Compensating the failed step itself.** Only steps that completed successfully need compensation. The step that failed has not committed any side effects.
- **Compensation that can also fail silently.** Log every compensation failure explicitly and surface it to an on-call alert. A failed compensation leaves the system in an inconsistent state that requires manual intervention.
- **Unbounded retries.** Without `MAX_COMPENSATION_RETRIES`, a broken compensation endpoint will loop forever and exhaust the DO's CPU time.

---

## Gotchas

- **Saga coordinators are not distributed locks.** Two requests with the same `orderId` will address the same DO, but the DO processes one request at a time — the second request will queue behind the first. This is the correct behaviour for order sagas.
- **DO eviction during a long saga.** A saga that takes more than 30 seconds risks DO eviction. Persist state to DO storage after every step. On the next request, load state from storage and resume from the last completed step.
- **`Promise.race` with `setTimeout` inside a Worker.** Workers support `setTimeout` for non-blocking delays, but the overall Worker request has a CPU time limit. Keep individual step timeouts under the Worker's wall-clock limit.
- **D1 `ON CONFLICT DO UPDATE` requires a unique constraint.** Ensure `saga_id` has `PRIMARY KEY` or a `UNIQUE` index in the `saga_history` table.

---

## Verification

```bash
# Happy path
curl -X POST https://your-worker.workers.dev/orders \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"order-001","userId":"u1","amount":99,"currency":"USD","items":[{"sku":"A","qty":1}],"shippingAddress":"123 Main St"}'
# Expect: {"status": "completed", ...}

# Simulate inventory failure (set INVENTORY_SERVICE_URL to a mock that returns 500)
# Expect: chargePayment compensated, status: "failed"
wrangler d1 execute YOUR_DB --command \
  "SELECT saga_id, order_id, status, steps FROM saga_history ORDER BY started_at DESC LIMIT 3;"
```

---

## Related

- `workers-inbox-outbox-pattern.md` — reliable event publishing used to trigger saga steps
- `workers-token-bucket-rate-limiter.md` — protect external services from saga retry storms
- Cloudflare Docs: [Durable Objects](https://developers.cloudflare.com/durable-objects/)
- Saga pattern reference: https://microservices.io/patterns/data/saga.html

---

## Sources

- Saga pattern — microservices.io: https://microservices.io/patterns/data/saga.html
- Compensating Transactions pattern — Azure Architecture Center: https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction
- Cloudflare Durable Objects docs: https://developers.cloudflare.com/durable-objects/
- Idempotency keys — Stripe Engineering: https://stripe.com/blog/idempotency
