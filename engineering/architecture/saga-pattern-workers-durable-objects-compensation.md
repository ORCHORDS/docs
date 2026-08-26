# Saga Pattern with Durable Objects for Distributed Transactions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A checkout flow spans three downstream services: payment gateway, inventory system, and notification service. A failure at step two must reverse the charge made at step one. Without coordination, the system ends up with inconsistent state — a charged card but no reserved stock.

## Context

Cloudflare Workers are stateless and short-lived. Durable Objects (DOs) provide a single-threaded, strongly-consistent storage layer that can act as a saga orchestrator. By storing saga state in DO storage, you gain durability across retries and network partitions without an external database for the coordination layer.

The saga pattern divides a distributed transaction into a sequence of local transactions, each with a corresponding compensating transaction that undoes its effect if a later step fails.

## SagaOrchestrator Durable Object

```typescript
// saga-orchestrator.ts
export interface SagaStep {
  name: string;
  status: 'pending' | 'completed' | 'compensated' | 'failed';
  result?: unknown;
  compensationResult?: unknown;
}

export interface SagaState {
  sagaId: string;
  orderId: string;
  steps: SagaStep[];
  status: 'running' | 'completed' | 'compensating' | 'failed';
  startedAt: string;
  finishedAt?: string;
}

export class SagaOrchestrator implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/start' && request.method === 'POST') {
      return this.startSaga(await request.json());
    }
    if (url.pathname === '/status') {
      const saga = await this.state.storage.get<SagaState>('saga');
      return Response.json(saga ?? { error: 'not found' });
    }
    return new Response('not found', { status: 404 });
  }

  private async startSaga(order: { orderId: string; amount: number; items: string[] }): Promise<Response> {
    const sagaId = crypto.randomUUID();
    const saga: SagaState = {
      sagaId,
      orderId: order.orderId,
      status: 'running',
      startedAt: new Date().toISOString(),
      steps: [
        { name: 'chargeCard', status: 'pending' },
        { name: 'reserveInventory', status: 'pending' },
        { name: 'sendConfirmation', status: 'pending' },
      ],
    };
    await this.state.storage.put('saga', saga);

    // Step 1: charge card
    try {
      const chargeResult = await this.chargeCard(order.orderId, order.amount);
      saga.steps[0] = { name: 'chargeCard', status: 'completed', result: chargeResult };
      await this.state.storage.put('saga', saga);
    } catch (err) {
      saga.steps[0].status = 'failed';
      saga.status = 'failed';
      saga.finishedAt = new Date().toISOString();
      await this.state.storage.put('saga', saga);
      await this.persistAudit(saga);
      return Response.json({ sagaId, status: 'failed', step: 'chargeCard' }, { status: 500 });
    }

    // Step 2: reserve inventory
    try {
      const reserveResult = await this.reserveInventory(order.orderId, order.items);
      saga.steps[1] = { name: 'reserveInventory', status: 'completed', result: reserveResult };
      await this.state.storage.put('saga', saga);
    } catch (err) {
      // Compensate step 1
      saga.status = 'compensating';
      await this.state.storage.put('saga', saga);
      const compResult = await this.refundCard(order.orderId, order.amount);
      saga.steps[0].status = 'compensated';
      saga.steps[0].compensationResult = compResult;
      saga.steps[1].status = 'failed';
      saga.status = 'failed';
      saga.finishedAt = new Date().toISOString();
      await this.state.storage.put('saga', saga);
      await this.persistAudit(saga);
      return Response.json({ sagaId, status: 'failed', step: 'reserveInventory' }, { status: 500 });
    }

    // Step 3: send confirmation (best-effort, no compensation needed)
    try {
      await this.sendConfirmation(order.orderId);
      saga.steps[2] = { name: 'sendConfirmation', status: 'completed' };
    } catch {
      saga.steps[2] = { name: 'sendConfirmation', status: 'failed' };
    }

    saga.status = 'completed';
    saga.finishedAt = new Date().toISOString();
    await this.state.storage.put('saga', saga);
    await this.persistAudit(saga);
    return Response.json({ sagaId, status: 'completed' });
  }

  private async chargeCard(orderId: string, amount: number): Promise<{ chargeId: string }> {
    const res = await fetch(`${this.env.PAYMENT_SERVICE_URL}/charge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderId, amount }),
    });
    if (!res.ok) throw new Error(`charge failed: ${res.status}`);
    return res.json();
  }

  private async refundCard(orderId: string, amount: number): Promise<{ refundId: string }> {
    const res = await fetch(`${this.env.PAYMENT_SERVICE_URL}/refund`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderId, amount }),
    });
    if (!res.ok) throw new Error(`refund failed: ${res.status}`);
    return res.json();
  }

  private async reserveInventory(orderId: string, items: string[]): Promise<{ reservationId: string }> {
    const res = await fetch(`${this.env.INVENTORY_SERVICE_URL}/reserve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderId, items }),
    });
    if (!res.ok) throw new Error(`reservation failed: ${res.status}`);
    return res.json();
  }

  private async sendConfirmation(orderId: string): Promise<void> {
    await fetch(`${this.env.NOTIFICATION_SERVICE_URL}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderId }),
    });
  }

  private async persistAudit(saga: SagaState): Promise<void> {
    await this.env.DB.prepare(
      `INSERT OR REPLACE INTO saga_audit
       (saga_id, order_id, status, steps_json, started_at, finished_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
      .bind(
        saga.sagaId,
        saga.orderId,
        saga.status,
        JSON.stringify(saga.steps),
        saga.startedAt,
        saga.finishedAt ?? null
      )
      .run();
  }
}
```

## Wiring the Worker Entry Point

Route incoming checkout requests to the appropriate DO instance, keyed by `orderId` so each order gets its own orchestrator.

```typescript
// worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/checkout' && request.method === 'POST') {
      const body = await request.json<{ orderId: string; amount: number; items: string[] }>();
      const id = env.SAGA_ORCHESTRATOR.idFromName(body.orderId);
      const stub = env.SAGA_ORCHESTRATOR.get(id);
      return stub.fetch(new Request('https://saga/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }));
    }
    return new Response('not found', { status: 404 });
  },
};
```

## D1 Audit Schema

```sql
CREATE TABLE IF NOT EXISTS saga_audit (
  saga_id     TEXT PRIMARY KEY,
  order_id    TEXT NOT NULL,
  status      TEXT NOT NULL,
  steps_json  TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  finished_at TEXT
);
CREATE INDEX idx_saga_order ON saga_audit(order_id);
```

## Anti-patterns

- **Shared DO instance across orders** — using a single DO for all sagas creates a serialisation bottleneck. Key by `orderId` so each saga runs independently.
- **Skipping DO storage between steps** — if you rely only on in-memory state and the DO is evicted mid-saga, the compensation log is lost. Always `storage.put` after each step.
- **Treating notifications as a saga step requiring compensation** — emails cannot be unsent. Model them as best-effort steps with no compensation; log the failure and move on.
- **Long-running sagas in a single DO alarm** — break long workflows into smaller chunks using DO alarms to avoid wall-clock limits.

## Gotchas

- Durable Object storage operations are transactional within a single `put`/`get` call but not across multiple awaits. If the DO is evicted between two `storage.put` calls, the second write may be lost. Batch state changes into a single `put` call where possible.
- The `SagaOrchestrator` class must be exported from `wrangler.toml` under `[[durable_objects]]` with the correct binding name.
- D1 `INSERT OR REPLACE` silently replaces rows; if your audit table uses foreign keys, use `INSERT OR IGNORE` and handle conflicts explicitly.

## Verification

```bash
# Trigger a successful saga
curl -X POST https://<worker>.workers.dev/checkout \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ord-001","amount":4999,"items":["sku-a","sku-b"]}'
# Expected: {"sagaId":"...","status":"completed"}

# Trigger a compensating saga (mock inventory service to return 500)
curl -X POST https://<worker>.workers.dev/checkout \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ord-002","amount":100,"items":["sku-out-of-stock"]}'
# Expected: {"sagaId":"...","status":"failed","step":"reserveInventory"}

# Query audit log
npx wrangler d1 execute <DB_NAME> \
  --command "SELECT saga_id, status, steps_json FROM saga_audit WHERE order_id='ord-002'"
```

## Related

- `bulkhead-pattern-workers-concurrency-isolation.md`
- `cqrs-workers-d1-read-write-separation.md`
- `domain-events-workers-queues-event-sourcing.md`

## Sources

- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- Chris Richardson, *Microservices Patterns*, Chapter 4 — Sagas
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
