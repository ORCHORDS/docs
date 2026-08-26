# Choreography vs Orchestration for Distributed Workflows

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A checkout flow spans five services: cart, inventory, payment, fulfillment, and notifications.
The team debates how to coordinate them. One engineer wires up a central "order workflow" service
that calls each downstream service in sequence (orchestration). Another argues for a pub/sub
approach where each service listens for events and acts independently (choreography).

Both work for simple flows. As the system grows, each approach develops distinct failure modes:
orchestrators become single points of failure and logic gravity wells; choreographed systems
become impossible to reason about globally ("who handles the compensating transaction if payment
fails after inventory is reserved?").

This document defines both patterns precisely, maps them to Cloudflare primitives, and gives a
decision framework for choosing — or combining — them.

---

## Context

**Orchestration** means a central coordinator explicitly invokes each step and handles the
outcome. The coordinator knows the full workflow: step order, retry logic, compensation on
failure. Examples: Temporal, AWS Step Functions, a Durable Object holding workflow state.

**Choreography** means each participant reacts to events without a central coordinator. Each
service knows only: "when I see event X, I do Y and emit event Z." No single component holds
the full picture. Examples: Kafka consumer groups, Cloudflare Queues + consumer Workers, event
buses.

**Key properties comparison:**

| Property                  | Orchestration                         | Choreography                        |
|---------------------------|---------------------------------------|-------------------------------------|
| Flow visibility           | Explicit in one place                 | Emergent — reconstructed from logs  |
| Coupling                  | Coordinator → all participants         | Event schema ↔ producers/consumers  |
| Single point of failure   | The orchestrator                      | Broker availability                 |
| Compensation (sagas)      | Orchestrator sends explicit rollback  | Compensating events published        |
| Testing                   | Unit-test the coordinator             | Integration-test event chains        |
| Scalability of participants| Steps run serially (unless parallel)  | Consumers scale independently        |
| Observability             | Coordinator holds state; easy to query| Requires distributed tracing         |

Neither is universally superior. Long-running, human-approval workflows suit orchestration;
high-throughput fan-out and decoupled service teams suit choreography.

---

## 1. Orchestration with Durable Objects

Durable Objects are ideal orchestrators: they maintain persistent state, handle retries with
Alarms, and provide a single address for the entire workflow instance.

```typescript
// workflow/src/order-orchestrator.ts
export interface OrderWorkflowState {
  orderId: string;
  step: 'init' | 'inventory' | 'payment' | 'fulfillment' | 'notified' | 'failed';
  reservationId?: string;
  paymentId?: string;
  attempts: Record<string, number>;
  createdAt: string;
}

export class OrderOrchestrator extends DurableObject {
  private state: OrderWorkflowState | null = null;

  async fetch(request: Request): Promise<Response> {
    const body = await request.json<{ action: string; payload?: unknown }>();

    switch (body.action) {
      case 'start':
        return this.start(body.payload as { orderId: string; items: unknown[] });
      case 'payment_confirmed':
        return this.onPaymentConfirmed(body.payload as { paymentId: string });
      case 'payment_failed':
        return this.onPaymentFailed();
      default:
        return new Response('Unknown action', { status: 400 });
    }
  }

  private async start(payload: { orderId: string; items: unknown[] }): Promise<Response> {
    this.state = {
      orderId: payload.orderId,
      step: 'inventory',
      attempts: {},
      createdAt: new Date().toISOString(),
    };
    await this.ctx.storage.put('state', this.state);

    // Step 1: Reserve inventory (synchronous call to inventory service)
    const reservationResponse = await fetch('https://inventory.internal/reserve', {
      method: 'POST',
      body: JSON.stringify({ orderId: payload.orderId, items: payload.items }),
    });

    if (!reservationResponse.ok) {
      return this.fail('inventory_reservation_failed');
    }

    const { reservationId } = await reservationResponse.json<{ reservationId: string }>();
    this.state.reservationId = reservationId;
    this.state.step = 'payment';
    await this.ctx.storage.put('state', this.state);

    // Step 2: Request payment (async — payment service will callback)
    await fetch('https://payment.internal/charge', {
      method: 'POST',
      body: JSON.stringify({
        orderId: payload.orderId,
        callbackUrl: `https://orchestrator.internal/orders/${payload.orderId}/payment_confirmed`,
      }),
    });

    // Set a timeout alarm in case payment never callbacks
    await this.ctx.storage.setAlarm(Date.now() + 30_000); // 30 seconds

    return new Response(JSON.stringify({ status: 'processing' }), { status: 202 });
  }

  async alarm(): Promise<void> {
    const state = await this.ctx.storage.get<OrderWorkflowState>('state');
    if (state?.step === 'payment') {
      // Payment callback never arrived — cancel
      await this.fail('payment_timeout');
    }
  }

  private async onPaymentConfirmed(payload: { paymentId: string }): Promise<Response> {
    if (!this.state || this.state.step !== 'payment') {
      return new Response('Unexpected state', { status: 409 });
    }
    this.state.paymentId = payload.paymentId;
    this.state.step = 'fulfillment';
    await this.ctx.storage.put('state', this.state);

    // Step 3: Trigger fulfillment
    await fetch('https://fulfillment.internal/create-shipment', {
      method: 'POST',
      body: JSON.stringify({ orderId: this.state.orderId, reservationId: this.state.reservationId }),
    });

    return new Response(JSON.stringify({ status: 'fulfillment_started' }), { status: 200 });
  }

  private async fail(reason: string): Promise<Response> {
    if (this.state?.reservationId) {
      // Compensate: release the reservation
      await fetch('https://inventory.internal/release', {
        method: 'POST',
        body: JSON.stringify({ reservationId: this.state.reservationId }),
      });
    }
    if (this.state) {
      this.state.step = 'failed';
      await this.ctx.storage.put('state', this.state);
    }
    return new Response(JSON.stringify({ status: 'failed', reason }), { status: 500 });
  }
}
```

---

## 2. Choreography with Cloudflare Queues

In choreography, each service owns a queue binding and publishes events autonomously. No central
coordinator exists.

```typescript
// inventory-worker/src/index.ts  (choreography participant)
export interface OrderPlacedEvent {
  orderId: string;
  items: Array<{ sku: string; qty: number }>;
}

export interface InventoryReservedEvent {
  orderId: string;
  reservationId: string;
}

export interface InventoryFailedEvent {
  orderId: string;
  reason: string;
}

export default {
  // Reacts to OrderPlaced — no knowledge of who published it
  async queue(
    batch: MessageBatch<OrderPlacedEvent>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const { orderId, items } = msg.body;
      try {
        const reservationId = await reserveStock(items, env.DB);

        // Emit success event — no knowledge of who listens
        await env.INVENTORY_EVENTS.send({
          type: 'InventoryReserved',
          orderId,
          reservationId,
        } satisfies InventoryReservedEvent & { type: string });

        msg.ack();
      } catch (err) {
        // Emit failure event — compensating logic lives in the listeners
        await env.INVENTORY_EVENTS.send({
          type: 'InventoryFailed',
          orderId,
          reason: (err as Error).message,
        } satisfies InventoryFailedEvent & { type: string });

        msg.ack(); // ack to prevent re-processing; failure is communicated via event
      }
    }
  },
};
```

```typescript
// payment-worker/src/index.ts
// Listens to InventoryReserved and triggers payment
export default {
  async queue(
    batch: MessageBatch<{ type: string; orderId: string; reservationId?: string }>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      if (msg.body.type !== 'InventoryReserved') {
        msg.ack(); // not for us — topic-based filtering at the consumer
        continue;
      }
      await initiatePayment(msg.body.orderId, env);
      msg.ack();
    }
  },
};
```

---

## 3. Hybrid Pattern — Orchestration at the Domain, Choreography at the Boundary

For complex internal workflows, use an orchestrator inside the bounded context. At the boundary
with other bounded contexts, publish integration events and let those contexts choreograph their
own responses. This avoids the "orchestrator spider" anti-pattern where one coordinator reaches
across many bounded contexts.

```
   ┌─────────────────── Orders BC ──────────────────────┐
   │                                                    │
   │  OrderOrchestrator (Durable Object)                │
   │    → inventory reservation (internal RPC)          │
   │    → payment charge (internal callback)            │
   │    → fulfillment (internal RPC)                    │
   │    → emits OrderFulfilled integration event ──────────────► Notifications BC
   │                                                    │                   │
   └────────────────────────────────────────────────────┘                   ▼
                                                                 (choreography)
                                                                 Email Worker
                                                                 SMS Worker
                                                                 Push Worker
```

The Notifications bounded context does not need to know about the order workflow steps. It listens
for `OrderFulfilled` and fans out notifications autonomously. Adding a new notification channel
(e.g., WhatsApp) does not require any change to the Orders orchestrator.

```typescript
// notifications-worker/src/index.ts
export default {
  async queue(
    batch: MessageBatch<{ type: string; orderId: string; customerId: string }>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      if (msg.body.type !== 'OrderFulfilled') {
        msg.ack();
        continue;
      }
      // Fan out to all notification channels in parallel
      await Promise.allSettled([
        env.EMAIL_QUEUE.send({ ...msg.body, channel: 'email' }),
        env.SMS_QUEUE.send({ ...msg.body, channel: 'sms' }),
        env.PUSH_QUEUE.send({ ...msg.body, channel: 'push' }),
      ]);
      msg.ack();
    }
  },
};
```

---

## 4. Observability: Reconstructing Choreography Flows

The hardest problem with choreography is answering "where is order X right now?" With no central
coordinator, you reconstruct state from events. Analytics Engine makes this tractable.

```typescript
// Emit a correlation event on every state transition (any participant)
function trackWorkflowStep(
  dataset: AnalyticsEngineDataset,
  opts: {
    correlationId: string;  // orderId — same across all participants
    step: string;           // e.g. 'InventoryReserved'
    participant: string;    // e.g. 'inventory-worker'
    durationMs: number;
    success: boolean;
  }
): void {
  dataset.writeDataPoint({
    indexes: [opts.correlationId, opts.step, opts.participant],
    doubles: [opts.durationMs, opts.success ? 1 : 0],
    blobs: [],
  });
}
```

```sql
-- Reconstruct the timeline for a specific order
SELECT
  index2 AS step,
  index3 AS participant,
  timestamp,
  double1 AS duration_ms,
  double2 AS success
FROM workflow_events
WHERE index1 = 'order-abc-123'
ORDER BY timestamp ASC;
```

---

## Anti-patterns

- **Central choreography "event router."** A service that re-broadcasts all events to all
  consumers is orchestration in disguise, but without the coordinator's clarity. Consumers should
  subscribe directly to relevant queues or topics.
- **Orchestrator that calls across bounded contexts.** If the orchestrator invokes payment,
  fulfillment, AND the notifications team's API, it has become a cross-context coupling hub.
  Use integration events at BC boundaries.
- **Choreography without correlation IDs.** When a choreographed flow fails, you cannot trace
  which step failed without a `correlationId` on every event. Establish this from event zero.
- **Synchronous RPC inside a choreography flow.** If the inventory consumer makes a synchronous
  HTTP call to payment, you have synchronous coupling dressed as event-driven. Keep the async
  boundary clean.
- **Missing compensating transactions in choreography.** When a downstream step fails, every
  preceding step must have a compensating event listener. If inventory reserved but payment
  failed, who releases the reservation? Define and test the compensation chain explicitly.

---

## Gotchas

- **Queue fan-out limits.** Cloudflare Queues does not natively support topic-based filtering
  or fan-out to multiple consumer queues from one message. Use a fan-out Worker that reads from
  a single queue and writes to N downstream queues based on event type.
- **Durable Object orchestrators lose pending alarms on graceful deletion.** If you delete a DO
  instance to cancel a workflow, any pending Alarm is also deleted — but in-flight callbacks
  could still arrive. Handle the "orphaned callback" case (the DO no longer exists or is in
  `failed` state).
- **Temporal coupling in orchestration callbacks.** If the orchestrator makes an async call and
  waits for a callback URL, the callback must arrive within the Alarm timeout. Tune the alarm
  to be longer than the P99 of the downstream step.

---

## Verification

```bash
# Orchestration: query DO state for a given workflow
curl https://orchestrator.internal/orders/order-abc-123/state \
  | jq '{step: .step, created: .createdAt}'

# Choreography: trace all events for a correlation ID via Analytics Engine
curl -sX POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"query": "SELECT index2, index3, timestamp, double2 FROM workflow_events WHERE index1 = '"'"'order-abc-123'"'"' ORDER BY timestamp"}' \
  | jq '.data'
```

---

## Related

- `saga-pattern-orchestration-choreography.md`
- `saga-pattern-orchestration.md`
- `saga-pattern-choreography.md`
- `event-driven-architecture-overview.md`
- `durable-object-alarm-api-scheduled-retry.md`
- `async-job-queue-cloudflare-queues-do.md`
- `domain-events-vs-integration-events.md`

---

## Sources

- Richardson, Chris. *Microservices Patterns.* Manning, 2018. Chapter 4: Sagas.
- Hohpe, Gregor & Woolf, Bobby. *Enterprise Integration Patterns.* Addison-Wesley, 2003.
- Fowler, Martin. "Patterns of Enterprise Application Architecture — Process Manager." martinfowler.com
- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Kleppmann, Martin. *Designing Data-Intensive Applications.* O'Reilly, 2017. Chapter 11.
