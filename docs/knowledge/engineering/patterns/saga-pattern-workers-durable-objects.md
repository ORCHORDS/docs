# Saga Orchestration Pattern with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A business process spans multiple microservices (payment, inventory, shipping) and a failure at any step must roll back earlier steps atomically. Without coordination, partial failures leave data in an inconsistent state across services. You need a durable, observable orchestrator that survives Worker restarts and can replay from the last successful step.

---

## Context

The Saga pattern models a long-running transaction as a sequence of local transactions, each with a corresponding compensating action. A Durable Object (DO) acts as the saga orchestrator: it persists step state in `state.storage`, calls downstream service bindings in order, and on failure walks backwards calling compensating transactions. Because Durable Objects survive the execution lifecycle of individual Workers, in-progress sagas are never lost on eviction. Each step is written idempotently so retries are safe. A saga log stored in the DO provides full observability without an external database.

---

## Schema — Saga State Shape

```typescript
// src/types/saga.ts
export type StepStatus = 'pending' | 'completed' | 'compensated' | 'failed';

export interface SagaStep {
  name: string;
  status: StepStatus;
  result?: unknown;
  error?: string;
  startedAt?: string;
  finishedAt?: string;
}

export interface SagaState {
  sagaId: string;
  sagaType: string;
  input: unknown;
  steps: SagaStep[];
  status: 'running' | 'completed' | 'compensating' | 'failed';
  createdAt: string;
  updatedAt: string;
}
```

---

## Implementation — Saga Durable Object

```typescript
// src/durable-objects/order-saga.ts
import { DurableObject } from 'cloudflare:workers';
import { Env } from '../types';
import { SagaState, SagaStep } from '../types/saga';

type StepDefinition = {
  name: string;
  execute: (input: unknown, env: Env) => Promise<unknown>;
  compensate: (result: unknown, env: Env) => Promise<void>;
};

const ORDER_STEPS: StepDefinition[] = [
  {
    name: 'reserve-inventory',
    async execute(input: any, env: Env) {
      const res = await env.INVENTORY_SERVICE.fetch('/reserve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orderId: input.orderId, items: input.items }),
      });
      if (!res.ok) throw new Error(`inventory reserve failed: ${res.status}`);
      return res.json();
    },
    async compensate(result: any, env: Env) {
      await env.INVENTORY_SERVICE.fetch('/release', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reservationId: result.reservationId }),
      });
    },
  },
  {
    name: 'charge-payment',
    async execute(input: any, env: Env) {
      const res = await env.PAYMENT_SERVICE.fetch('/charge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          orderId: input.orderId,
          amountCents: input.totalCents,
          userId: input.userId,
        }),
      });
      if (!res.ok) throw new Error(`payment charge failed: ${res.status}`);
      return res.json();
    },
    async compensate(result: any, env: Env) {
      await env.PAYMENT_SERVICE.fetch('/refund', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chargeId: result.chargeId }),
      });
    },
  },
  {
    name: 'create-shipment',
    async execute(input: any, env: Env) {
      const res = await env.SHIPPING_SERVICE.fetch('/shipments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          orderId: input.orderId,
          address: input.shippingAddress,
        }),
      });
      if (!res.ok) throw new Error(`shipment creation failed: ${res.status}`);
      return res.json();
    },
    async compensate(result: any, env: Env) {
      await env.SHIPPING_SERVICE.fetch(`/shipments/${result.shipmentId}/cancel`, {
        method: 'DELETE',
      });
    },
  },
];

export class OrderSagaDO extends DurableObject<Env> {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/start') {
      const input = await request.json();
      return this.startSaga(input);
    }
    if (request.method === 'GET' && url.pathname === '/status') {
      return this.getStatus();
    }
    return new Response('Not found', { status: 404 });
  }

  private async startSaga(input: unknown): Promise<Response> {
    const existingState = await this.ctx.storage.get<SagaState>('state');
    if (existingState && existingState.status === 'completed') {
      return Response.json({ status: 'already-completed', state: existingState });
    }

    const sagaId = crypto.randomUUID();
    const now = new Date().toISOString();
    const state: SagaState = {
      sagaId,
      sagaType: 'order-fulfillment',
      input,
      steps: ORDER_STEPS.map((s) => ({ name: s.name, status: 'pending' })),
      status: 'running',
      createdAt: now,
      updatedAt: now,
    };
    await this.ctx.storage.put('state', state);

    // Run orchestration in background so the response returns quickly
    this.ctx.waitUntil(this.orchestrate(state, input));

    return Response.json({ sagaId, status: 'started' }, { status: 202 });
  }

  private async orchestrate(state: SagaState, input: unknown): Promise<void> {
    const completedResults: unknown[] = [];

    for (let i = 0; i < ORDER_STEPS.length; i++) {
      const stepDef = ORDER_STEPS[i];
      const step = state.steps[i];

      // Idempotency: skip already-completed steps on retry
      if (step.status === 'completed') {
        completedResults.push(step.result);
        continue;
      }

      step.status = 'pending';
      step.startedAt = new Date().toISOString();
      await this.persist(state);

      try {
        const result = await stepDef.execute(input, this.env);
        step.status = 'completed';
        step.result = result;
        step.finishedAt = new Date().toISOString();
        completedResults.push(result);
        await this.persist(state);
      } catch (err: any) {
        step.status = 'failed';
        step.error = err.message;
        step.finishedAt = new Date().toISOString();
        state.status = 'compensating';
        await this.persist(state);
        await this.compensate(state, completedResults, i - 1);
        return;
      }
    }

    state.status = 'completed';
    await this.persist(state);
  }

  private async compensate(
    state: SagaState,
    results: unknown[],
    fromStep: number,
  ): Promise<void> {
    for (let i = fromStep; i >= 0; i--) {
      const stepDef = ORDER_STEPS[i];
      const step = state.steps[i];
      try {
        await stepDef.compensate(results[i], this.env);
        step.status = 'compensated';
      } catch (err: any) {
        step.error = `compensation failed: ${err.message}`;
      }
      await this.persist(state);
    }
    state.status = 'failed';
    await this.persist(state);
  }

  private async persist(state: SagaState): Promise<void> {
    state.updatedAt = new Date().toISOString();
    await this.ctx.storage.put('state', state);
  }

  private async getStatus(): Promise<Response> {
    const state = await this.ctx.storage.get<SagaState>('state');
    if (!state) return new Response('Not found', { status: 404 });
    return Response.json(state);
  }
}
```

---

## Integration — Gateway Worker

```typescript
// src/index.ts
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST' && new URL(request.url).pathname === '/orders') {
      const body = await request.json<{ orderId: string }>();
      // One DO per order — orderId is the unique key
      const id = env.ORDER_SAGA.idFromName(body.orderId);
      const stub = env.ORDER_SAGA.get(id);
      return stub.fetch(new Request('https://saga/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }));
    }
    if (request.method === 'GET') {
      const sagaId = new URL(request.url).searchParams.get('orderId') ?? '';
      const id = env.ORDER_SAGA.idFromName(sagaId);
      const stub = env.ORDER_SAGA.get(id);
      return stub.fetch(new Request('https://saga/status'));
    }
    return new Response('Not found', { status: 404 });
  },
};
```

---

## Anti-patterns

- **Running saga steps synchronously in the request handler** — a Worker timeout kills the process mid-saga, leaving no durable state; always use `ctx.waitUntil()` or a DO alarm for long orchestrations.
- **Storing mutable step results in Worker memory** — Worker instances are not shared; always persist step results to DO storage before moving to the next step.
- **Skipping idempotency checks** — if the DO is retried after a crash mid-step, re-executing a completed step causes double-charges; check `step.status === 'completed'` before executing.
- **Ignoring compensation failures** — log and alert on failed compensations; they require manual remediation.

---

## Gotchas

- DO storage operations are linearizable within a single DO instance; concurrent writes to the same saga will be serialized automatically.
- The `waitUntil()` budget on a DO is 30 seconds per request; use DO alarms (`this.ctx.storage.setAlarm()`) for sagas that may take minutes.
- `idFromName()` with the same string always returns the same DO — guarantee exactly one orchestrator per saga by using a stable business key (e.g., `orderId`).
- Cross-zone service binding calls add ~5 ms latency each; keep step count reasonable (under 10) or pipeline where possible.

---

## Verification

```bash
# Start a saga
curl -X POST https://my-worker.example.com/orders \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ord_123","userId":"u1","totalCents":9900,"items":[{"sku":"A","qty":2}],"shippingAddress":"123 Main St"}'

# Poll status
curl 'https://my-worker.example.com/orders?orderId=ord_123'

# Inspect DO storage via wrangler
wrangler durable-objects storage list ORDER_SAGA --remote
```

---

## Related

- `outbox-pattern-workers-d1-queues.md`
- `bulkhead-pattern-workers-concurrency-limit.md`
- `retry-with-jitter-pattern-workers.md`

---

## Sources

- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Cloudflare DO Storage API — https://developers.cloudflare.com/durable-objects/api/storage-api/
- Microservices Patterns — Saga — https://microservices.io/patterns/data/saga.html
