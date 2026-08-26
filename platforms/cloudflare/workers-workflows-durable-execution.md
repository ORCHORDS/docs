# Durable Execution with Cloudflare Workflows

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A multi-step business process (order fulfilment, user onboarding, payment reconciliation) must complete reliably even when individual steps fail, the Worker is evicted mid-run, or the process takes hours. Plain `fetch()` handlers time out after 30 seconds and have no durable state — a crash loses all progress.

## Context

Cloudflare Workflows provides durable execution on top of Workers. A Workflow is a class that extends `WorkflowEntrypoint`; its `run()` method orchestrates a sequence of `step()` calls. Each step is persisted to durable storage before and after execution. If the Worker is interrupted, Workflows replays the execution from the last completed step — completed step results are not re-executed, only the step that failed is retried.

Key primitives:
- `step.do(name, fn)` — execute a durable step; result is persisted.
- `step.sleep(name, duration)` — pause execution for a duration without holding a Worker CPU slot.
- `step.waitForEvent(name, options)` — block until an external event is sent into the Workflow instance.
- Automatic retries with configurable backoff per step.
- Workflow instances can run for up to 1 year (with sleep).

## Solution

### 1. wrangler.toml Configuration

```toml
# wrangler.toml
name = "order-processor"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[workflows]]
binding = "ORDER_WORKFLOW"
name = "order-workflow"
class_name = "OrderWorkflow"

[[d1_databases]]
binding = "DB"
database_name = "orders-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[queues.producers]]
binding = "NOTIFICATION_QUEUE"
queue = "order-notifications"
```

### 2. TypeScript Types

```typescript
// src/types.ts
export interface Env {
  ORDER_WORKFLOW: Workflow;
  DB: D1Database;
  NOTIFICATION_QUEUE: Queue;
}

export interface OrderInput {
  orderId: string;
  userId: string;
  items: Array<{ productId: string; quantity: number; unitPrice: number }>;
  paymentMethodId: string;
}

export interface PaymentResult {
  transactionId: string;
  status: 'captured' | 'declined';
  amount: number;
}

export interface FulfilmentResult {
  warehouseRef: string;
  estimatedDelivery: string;
}
```

### 3. Workflow Class Definition

```typescript
// src/workflows/order.ts
import {
  WorkflowEntrypoint,
  WorkflowStep,
  WorkflowEvent,
} from 'cloudflare:workers';
import type { Env, OrderInput, PaymentResult, FulfilmentResult } from '../types';

export class OrderWorkflow extends WorkflowEntrypoint<Env, OrderInput> {
  async run(event: WorkflowEvent<OrderInput>, step: WorkflowStep): Promise<void> {
    const order = event.payload;
    console.log(`[${order.orderId}] Workflow started`);

    // Step 1: Validate inventory — retried automatically on failure
    const inventoryOk = await step.do(
      'validate-inventory',
      { retries: { limit: 3, delay: '5 seconds', backoff: 'exponential' } },
      async () => {
        return await this.checkInventory(order);
      }
    );

    if (!inventoryOk) {
      await step.do('mark-failed-inventory', async () => {
        await this.env.DB.prepare(
          "UPDATE orders SET status = 'failed', failure_reason = 'out_of_stock' WHERE id = ?1"
        ).bind(order.orderId).run();
      });
      return; // Workflow ends here — no further steps
    }

    // Step 2: Reserve inventory (idempotent — safe to retry)
    await step.do(
      'reserve-inventory',
      { retries: { limit: 5, delay: '2 seconds', backoff: 'linear' } },
      async () => {
        await this.reserveInventory(order);
      }
    );

    // Step 3: Charge payment
    const payment = await step.do<PaymentResult>(
      'charge-payment',
      { retries: { limit: 2, delay: '10 seconds', backoff: 'exponential' } },
      async () => {
        return await this.chargePayment(order);
      }
    );

    if (payment.status === 'declined') {
      await step.do('release-inventory-on-decline', async () => {
        await this.releaseInventory(order);
      });
      await step.do('mark-failed-payment', async () => {
        await this.env.DB.prepare(
          "UPDATE orders SET status = 'payment_failed' WHERE id = ?1"
        ).bind(order.orderId).run();
      });
      return;
    }

    // Step 4: Submit to warehouse
    const fulfilment = await step.do<FulfilmentResult>(
      'submit-to-warehouse',
      { retries: { limit: 10, delay: '30 seconds', backoff: 'exponential' } },
      async () => {
        return await this.submitToWarehouse(order, payment);
      }
    );

    // Step 5: Wait for warehouse confirmation (external event, up to 48h)
    const confirmation = await step.waitForEvent<{ confirmed: boolean }>(
      'warehouse-confirmation',
      { timeout: '48 hours' }
    );

    if (!confirmation.payload.confirmed) {
      await step.do('handle-warehouse-rejection', async () => {
        await this.refundPayment(payment);
      });
      return;
    }

    // Step 6: Update DB and notify customer
    await step.do('mark-confirmed', async () => {
      await this.env.DB.prepare(
        "UPDATE orders SET status = 'confirmed', warehouse_ref = ?1, estimated_delivery = ?2 WHERE id = ?3"
      )
        .bind(fulfilment.warehouseRef, fulfilment.estimatedDelivery, order.orderId)
        .run();
    });

    // Step 7: Sleep 1 hour, then send dispatch notification
    await step.sleep('wait-before-dispatch-notification', '1 hour');

    await step.do('send-dispatch-notification', async () => {
      await this.env.NOTIFICATION_QUEUE.send({
        type: 'order.dispatched',
        orderId: order.orderId,
        userId: order.userId,
        warehouseRef: fulfilment.warehouseRef,
        estimatedDelivery: fulfilment.estimatedDelivery,
      });
    });

    console.log(`[${order.orderId}] Workflow completed successfully`);
  }

  // --- Private helpers (called inside step.do closures) ---

  private async checkInventory(order: OrderInput): Promise<boolean> {
    // Query inventory service — abbreviated
    for (const item of order.items) {
      const row = await this.env.DB.prepare(
        'SELECT stock FROM products WHERE id = ?1'
      ).bind(item.productId).first<{ stock: number }>();
      if (!row || row.stock < item.quantity) return false;
    }
    return true;
  }

  private async reserveInventory(order: OrderInput): Promise<void> {
    const stmts = order.items.map((item) =>
      this.env.DB.prepare(
        'UPDATE products SET stock = stock - ?1, reserved = reserved + ?1 WHERE id = ?2 AND stock >= ?1'
      ).bind(item.quantity, item.productId)
    );
    await this.env.DB.batch(stmts);
  }

  private async chargePayment(order: OrderInput): Promise<PaymentResult> {
    // Call payment processor — return mocked result here
    const total = order.items.reduce((s, i) => s + i.quantity * i.unitPrice, 0);
    return { transactionId: `txn_${order.orderId}`, status: 'captured', amount: total };
  }

  private async submitToWarehouse(
    order: OrderInput,
    payment: PaymentResult
  ): Promise<FulfilmentResult> {
    // POST to warehouse API — abbreviated
    return {
      warehouseRef: `WH-${order.orderId}`,
      estimatedDelivery: new Date(Date.now() + 3 * 86400000).toISOString().split('T')[0],
    };
  }

  private async releaseInventory(order: OrderInput): Promise<void> {
    const stmts = order.items.map((item) =>
      this.env.DB.prepare(
        'UPDATE products SET stock = stock + ?1, reserved = reserved - ?1 WHERE id = ?2'
      ).bind(item.quantity, item.productId)
    );
    await this.env.DB.batch(stmts);
  }

  private async refundPayment(payment: PaymentResult): Promise<void> {
    console.log(`Refunding transaction ${payment.transactionId} for ${payment.amount}`);
    // Call payment processor refund endpoint
  }
}
```

### 4. Triggering a Workflow from an HTTP Handler

```typescript
// src/index.ts
import type { Env, OrderInput } from './types';
import { OrderWorkflow } from './workflows/order';

export { OrderWorkflow };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /orders — start a new workflow instance
    if (url.pathname === '/orders' && request.method === 'POST') {
      const body = await request.json<OrderInput>();

      // Create workflow instance — returns immediately, execution is async
      const instance = await env.ORDER_WORKFLOW.create({
        id: body.orderId,   // Deterministic ID — idempotent creation
        params: body,
      });

      return Response.json(
        { instanceId: instance.id, status: 'started' },
        { status: 202 }
      );
    }

    // GET /orders/:id/status — poll workflow status
    if (url.pathname.startsWith('/orders/') && url.pathname.endsWith('/status')) {
      const orderId = url.pathname.split('/')[2];
      const instance = await env.ORDER_WORKFLOW.get(orderId);
      const status = await instance.status();

      return Response.json({
        instanceId: orderId,
        status: status.status,
        output: status.output,
        error: status.error,
      });
    }

    // POST /orders/:id/confirm — send external event into running workflow
    if (url.pathname.match(/^\/orders\/[^/]+\/confirm$/)) {
      const orderId = url.pathname.split('/')[2];
      const body = await request.json<{ confirmed: boolean }>();
      const instance = await env.ORDER_WORKFLOW.get(orderId);

      await instance.sendEvent({
        name: 'warehouse-confirmation',
        payload: body,
      });

      return Response.json({ sent: true });
    }

    return Response.json({ error: 'Not found' }, { status: 404 });
  },
};
```

### 5. Workflow Status Polling

```typescript
// src/status-checker.ts
import type { Env } from './types';

type WorkflowStatus = 'queued' | 'running' | 'paused' | 'complete' | 'errored' | 'terminated';

export async function pollUntilDone(
  env: Env,
  instanceId: string,
  timeoutMs = 60_000
): Promise<WorkflowStatus> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const instance = await env.ORDER_WORKFLOW.get(instanceId);
    const { status } = await instance.status();

    if (['complete', 'errored', 'terminated'].includes(status)) {
      return status as WorkflowStatus;
    }

    // Back off between polls — Workflows are async, not real-time
    await new Promise((r) => setTimeout(r, 2000));
  }

  return 'running'; // Still in progress at deadline
}
```

## Implementation Details

**Replay semantics:** When a Workflow resumes after an interruption, `run()` is re-entered from the top. The Workflows runtime intercepts `step.do()` calls and returns the previously persisted result for completed steps without re-executing the closure. Code **outside** a `step.do()` closure runs on every replay — keep it side-effect-free.

**Step naming:** Step names must be unique within a `run()` invocation. They are the keys used to look up persisted results during replay. Dynamic names like `step-${i}` are valid but must be deterministic across replays.

**Retry configuration:** Each `step.do()` accepts independent retry options. The default is 3 retries with exponential backoff. Steps that call idempotent external APIs should have higher retry limits; non-idempotent steps (e.g., charge payment) should have low limits or manual idempotency guards.

**waitForEvent timeout:** If the external event is not received within the timeout, the step throws a `WorkflowTimeoutError`. Catch it inside `run()` to implement timeout-handling logic.

**Workflow instance ID:** Passing a deterministic `id` (e.g., the order ID) when creating an instance makes creation idempotent — calling `create()` with the same ID twice returns the existing instance rather than starting a duplicate.

**CPU time:** Workers inside Workflows still observe the 30-second CPU time limit per activation. Long compute must be broken into steps. `step.sleep()` releases the CPU between steps.

## Anti-patterns

- Do not perform side effects (DB writes, API calls) outside a `step.do()` closure — they will re-execute on every replay.
- Do not use `Math.random()`, `Date.now()`, or `crypto.randomUUID()` outside a `step.do()` closure — replay will produce different values, causing divergence.
- Do not catch all errors in a step and return a sentinel — let errors propagate so the Workflows runtime can trigger retries.
- Do not poll `instance.status()` in a tight loop from a Workflow — use `step.waitForEvent()` for external signals instead.

## Gotchas

- Workflows are in open beta as of mid-2024. The API surface may change — pin `compatibility_date` and test after Cloudflare releases updates.
- `step.sleep()` durations are not exact — treat them as minimums. Long sleeps (hours/days) are reliable; sub-minute sleeps may have a few seconds of variance.
- The Workflows runtime serialises step results as JSON. Return values from `step.do()` must be JSON-serialisable — no `Date` objects, `Map`, `Set`, or class instances (convert to plain objects).
- Terminating a Workflow instance via `instance.terminate()` does not trigger cleanup steps — implement compensation logic explicitly before terminating.

## Verification

```bash
# Deploy the worker with workflow binding
npx wrangler deploy

# Start a workflow instance
curl -X POST https://order-processor.example.com/orders \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ord-001","userId":"usr-1","items":[{"productId":"p-1","quantity":2,"unitPrice":29.99}],"paymentMethodId":"pm_test"}'

# Poll status
curl https://order-processor.example.com/orders/ord-001/status

# Send external event (warehouse confirmation)
curl -X POST https://order-processor.example.com/orders/ord-001/confirm \
  -H 'Content-Type: application/json' \
  -d '{"confirmed":true}'

# Tail workflow logs
npx wrangler tail --format pretty
```

## Related

- `workers-queues-fan-out-pattern.md` — triggering a workflow from a queue consumer
- `workers-hyperdrive-postgres-connection.md` — persisting workflow state to Postgres
- Workflows docs: https://developers.cloudflare.com/workflows/

## Sources

- https://developers.cloudflare.com/workflows/get-started/
- https://developers.cloudflare.com/workflows/reference/step-primitives/
- https://developers.cloudflare.com/workflows/reference/retry-errors/
- https://developers.cloudflare.com/workflows/reference/lifecycle-and-state/
