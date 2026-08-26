# feature-cookbook-saga

**Issue:** Saga pattern — distributed transactions, compensation
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a "place order" flow: charge the user, reserve
inventory, send a confirmation email, create a shipment.
The charge succeeds. The inventory reservation fails.
The user is charged but has no order. The team scrambles
to refund. You wish you'd had a saga.

## Root cause
**Distributed transactions are hard.** Use a saga with
compensation.

**Source:** Garcia-Molina — Sagas:
https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf

## The "saga" concept

A saga is a sequence of local transactions. Each local
transaction has a compensation action that undoes it.

```
Step 1: Charge user     → Compensate: Refund user
Step 2: Reserve inventory → Compensate: Release inventory
Step 3: Send email       → Compensate: Send "your order failed" email
Step 4: Create shipment  → Compensate: Cancel shipment
```

If any step fails, the previous steps' compensations run.

## The "orchestrated saga" pattern

For an orchestrated saga, a central coordinator:
```ts
async function placeOrderSaga(order: Order, env: Env): Promise<void> {
  const sagaState: SagaState = {
    orderId: order.id,
    step: 0,
    compensations: [],
  };

  try {
    // Step 1: Charge
    const charge = await chargeUser(order, env);
    sagaState.compensations.push(() => refundUser(charge.id, env));
    sagaState.step = 1;

    // Step 2: Reserve inventory
    const reservation = await reserveInventory(order, env);
    sagaState.compensations.push(() => releaseInventory(reservation.id, env));
    sagaState.step = 2;

    // Step 3: Send email
    await sendConfirmationEmail(order, env);
    sagaState.compensations.push(() => sendFailureEmail(order, env));
    sagaState.step = 3;

    // Step 4: Create shipment
    await createShipment(order, env);
    sagaState.compensations.push(() => cancelShipment(order, env));
    sagaState.step = 4;

    // Success!
  } catch (err) {
    // Compensate in reverse order
    for (const compensation of sagaState.compensations.reverse()) {
      try {
        await compensation();
      } catch (compensationErr) {
        // Log; alert
        logEvent('saga.compensation.failed', 'error', { error: String(compensationErr) });
      }
    }

    throw err;
  }
}
```

The saga is orchestrated; compensations run on failure.

## The "choreographed saga" pattern

For a choreographed saga, the services communicate via
events:
```ts
// 1. Order service creates the order
await env.DB!.prepare(`INSERT INTO orders ...`).run();
await env.QUEUE.send({ type: 'order.created', orderId });

// 2. Payment service handles payment
async function handleOrderCreated(event: Event, env: Env) {
  await chargeUser(event.orderId, env);
  await env.QUEUE.send({ type: 'order.paid', orderId: event.orderId });
}

// 3. Inventory service reserves
async function handleOrderPaid(event: Event, env: Env) {
  await reserveInventory(event.orderId, env);
  await env.QUEUE.send({ type: 'order.reserved', orderId: event.orderId });
}

// ... etc
```

The saga is choreographed; each service reacts to events.

## The "saga state" pattern

For a long-running saga, persist the state:
```sql
CREATE TABLE saga_state (
  id TEXT PRIMARY KEY,
  saga_type TEXT NOT NULL,  -- 'place_order', 'cancel_order', etc.
  step INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,  -- 'running', 'completed', 'failed', 'compensating'
  data TEXT,  -- JSON
  started_at TEXT DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
);
```

The saga state is persisted; the saga can be resumed.

## The "compensation" pattern

For each step, define a compensation:
```ts
interface SagaStep {
  action: () => Promise<void>;
  compensation: () => Promise<void>;
}

const placeOrderSteps: SagaStep[] = [
  {
    action: async () => { await chargeUser(); },
    compensation: async () => { await refundCharge(); },
  },
  {
    action: async () => { await reserveInventory(); },
    compensation: async () => { await releaseInventory(); },
  },
  // ...
];
```

The step + compensation are paired.

## The "idempotent compensation" pattern

For compensation, idempotency is critical:
```ts
async function refundCharge(chargeId: string, env: Env): Promise<void> {
  // Idempotency: refund the same charge only once
  const refunded = await env.KV.get(`refunded:${chargeId}`);
  if (refunded) return;

  await stripe.refunds.create({ charge: chargeId });
  await env.KV.put(`refunded:${chargeId}`, '1', { expirationTtl: 86400 * 30 });
}
```

The compensation is idempotent.

## The "saga timeout" pattern

For a long-running saga, set a timeout:
```ts
async function placeOrderSaga(order: Order, env: Env): Promise<void> {
  const start = Date.now();
  const TIMEOUT = 5 * 60 * 1000;  // 5 min

  for (const step of steps) {
    if (Date.now() - start > TIMEOUT) {
      throw new Error('Saga timeout');
    }
    await step.action();
  }
}
```

A timeout prevents indefinite waiting.

## The "saga retry" pattern

For a transient failure, retry the step:
```ts
async function withRetry(fn: () => Promise<void>, maxAttempts = 3): Promise<void> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      await fn();
      return;
    } catch (err) {
      if (attempt === maxAttempts - 1) throw err;
      if (!isRetryable(err)) throw err;
      await sleep(2 ** attempt * 1000);
    }
  }
}
```

The step is retried before compensating.

## The "saga visibility" pattern

For a saga dashboard:
- **Running sagas:** Count + step
- **Failed sagas:** Count + step + error
- **Compensating sagas:** Count + which compensations
- **Long-running sagas:** Sagas that have been running for
  > 1 hour

The dashboard shows the saga health.

## The "saga anti-pattern" anti-patterns

### 1. No compensation
- **Issue:** A failed step leaves the system in an
  inconsistent state
- **Fix:** Define a compensation for every step

### 2. Compensations that fail
- **Issue:** A compensation error leaves the system in an
  inconsistent state
- **Fix:** Alert + manual intervention; don't fail silently

### 3. Long-running sagas
- **Issue:** A saga that takes hours is hard to debug
- **Fix:** Keep sagas short; break into smaller sagas

### 4. No saga state
- **Issue:** A saga that crashes can't be resumed
- **Fix:** Persist saga state

### 5. Idempotency missing
- **Issue:** A retry does the work twice
- **Fix:** Idempotency keys

## The "saga vs 2PC" choice

| Use case | Use |
|---|---|
| **Single DB** | Local transaction |
| **Multiple services** | Saga |
| **Strong consistency required** | 2PC (rare; expensive) |
| **Eventual consistency OK** | Saga |

For most apps, **saga** is the right answer.

## Verification
- **Test:** Saga runs to completion
- **Test:** Saga compensates on failure
- **Test:** Saga retries on transient failure
- **Live:** Saga dashboard is monitored
- **Audit:** Annual review of sagas

## Gotchas
- **The "no compensation" anti-pattern.** A failed step
  leaves the system inconsistent.
- **The "compensation that fails" anti-pattern.** Always
  log + alert on compensation failure.
- **The "saga in a single Worker" anti-pattern.** A
  long-running saga is killed by the Worker timeout.
- **The "no saga state" anti-pattern.** A saga that
  crashes can't be resumed.

## Related
- `saga-pattern.md`
- `event-sourcing.md`
- `idempotency-keys.md`
- `retry-with-exponential-backoff.md`
- `cloudflare/workers-workers-queues-patterns.md`
- `feature-cookbook-state-machines.md`
- Temporal: https://temporal.io/
- Cadence: https://cadenceworkflow.io/
