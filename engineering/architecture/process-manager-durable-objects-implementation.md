# Process Manager Pattern — Durable Objects Implementation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a multi-step business process (order fulfilment, user onboarding, loan
approval) that spans several services and can run for minutes, hours, or days.
A choreography saga becomes impossible to debug once you exceed four or five steps.
You need a single, inspectable, stateful coordinator that remembers where the process
is, reacts to incoming events, sends commands, and handles timeouts.

## Context

The **Process Manager** (also called Orchestrating Saga) is a stateful entity that:

1. Listens for domain events.
2. Decides what command to issue next based on current state.
3. Tracks which steps have completed and which are still pending.
4. Handles timeouts via scheduled alarms.
5. Can be suspended and resumed across arbitrary time spans.

Durable Objects are an exact fit: they are long-lived, have persistent storage,
support WebSocket hibernation, and expose the Alarm API. One DO instance = one
process instance, identified by the process's natural key (e.g., order ID).

## State Machine Definition

Define process states as a discriminated union so TypeScript enforces valid
transitions.

```typescript
// process/order-fulfilment-state.ts
export type FulfilmentState =
  | { status: 'AwaitingPayment'; orderId: string; startedAt: string }
  | { status: 'AwaitingWarehousePick'; orderId: string; paymentRef: string }
  | { status: 'AwaitingShipment'; orderId: string; pickId: string }
  | { status: 'Completed'; orderId: string; trackingId: string }
  | { status: 'Compensating'; orderId: string; reason: string; step: string }
  | { status: 'Failed'; orderId: string; reason: string };

export type FulfilmentEvent =
  | { type: 'PaymentConfirmed'; orderId: string; paymentRef: string }
  | { type: 'PickCompleted'; orderId: string; pickId: string }
  | { type: 'ShipmentDispatched'; orderId: string; trackingId: string }
  | { type: 'PaymentFailed'; orderId: string; reason: string }
  | { type: 'PickFailed'; orderId: string; reason: string };
```

## Durable Object Process Manager

```typescript
// process/order-fulfilment-manager.ts
const PAYMENT_TIMEOUT_MS = 15 * 60 * 1000; // 15 min

export class OrderFulfilmentManager extends DurableObject {
  private state!: FulfilmentState;

  async start(orderId: string): Promise<void> {
    this.state = { status: 'AwaitingPayment', orderId, startedAt: new Date().toISOString() };
    await this.persist();
    // Set timeout alarm
    await this.ctx.storage.setAlarm(Date.now() + PAYMENT_TIMEOUT_MS);
    await this.sendCommand('RequestPayment', { orderId });
  }

  async handle(event: FulfilmentEvent): Promise<void> {
    await this.loadState();
    this.state = this.transition(this.state, event);
    await this.persist();
    await this.react(this.state, event);
  }

  private transition(state: FulfilmentState, event: FulfilmentEvent): FulfilmentState {
    if (state.status === 'AwaitingPayment' && event.type === 'PaymentConfirmed') {
      return { status: 'AwaitingWarehousePick', orderId: state.orderId, paymentRef: event.paymentRef };
    }
    if (state.status === 'AwaitingWarehousePick' && event.type === 'PickCompleted') {
      return { status: 'AwaitingShipment', orderId: state.orderId, pickId: event.pickId };
    }
    if (state.status === 'AwaitingShipment' && event.type === 'ShipmentDispatched') {
      return { status: 'Completed', orderId: state.orderId, trackingId: event.trackingId };
    }
    if (event.type === 'PaymentFailed') {
      return { status: 'Failed', orderId: state.orderId, reason: event.reason };
    }
    if (event.type === 'PickFailed') {
      return { status: 'Compensating', orderId: state.orderId, reason: event.reason, step: 'RefundPayment' };
    }
    return state; // no valid transition — idempotent
  }

  private async react(state: FulfilmentState, _event: FulfilmentEvent): Promise<void> {
    switch (state.status) {
      case 'AwaitingWarehousePick':
        await this.ctx.storage.setAlarm(Date.now() + 30 * 60 * 1000);
        await this.sendCommand('RequestPick', { orderId: state.orderId });
        break;
      case 'AwaitingShipment':
        await this.ctx.storage.setAlarm(Date.now() + 60 * 60 * 1000);
        await this.sendCommand('RequestShipment', { orderId: state.orderId, pickId: state.pickId });
        break;
      case 'Compensating':
        await this.sendCommand(state.step, { orderId: state.orderId });
        break;
      case 'Completed':
        await this.ctx.storage.deleteAlarm();
        break;
    }
  }

  async alarm(): Promise<void> {
    await this.loadState();
    // Timeout — escalate or compensate
    if (this.state.status === 'AwaitingPayment') {
      this.state = { status: 'Failed', orderId: (this.state as any).orderId, reason: 'PaymentTimeout' };
      await this.persist();
    } else {
      // Re-arm and retry current step's command
      await this.ctx.storage.setAlarm(Date.now() + 5 * 60 * 1000);
      await this.react(this.state, { type: 'PaymentFailed', orderId: '', reason: 'retry' });
    }
  }

  private async persist(): Promise<void> {
    await this.ctx.storage.put('state', this.state);
  }

  private async loadState(): Promise<void> {
    this.state = (await this.ctx.storage.get<FulfilmentState>('state'))!;
  }

  private async sendCommand(command: string, payload: Record<string, unknown>): Promise<void> {
    await (this as any).env.COMMAND_QUEUE.send({ command, ...payload });
  }
}
```

## Routing Events into the Process Manager

A Queue consumer worker routes incoming domain events to the correct DO instance
using the orderId as the DO name key.

```typescript
// router/fulfilment-event-router.ts
export default {
  async queue(batch: MessageBatch<FulfilmentEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { orderId } = msg.body as any;
      if (!orderId) { msg.ack(); continue; }

      const id = env.ORDER_FULFILMENT.idFromName(orderId);
      const stub = env.ORDER_FULFILMENT.get(id);
      await stub.handle(msg.body);
      msg.ack();
    }
  },
};
```

## Inspecting Process State

Expose a GET endpoint on the DO for operational visibility.

```typescript
async fetch(request: Request): Promise<Response> {
  if (new URL(request.url).pathname === '/state') {
    await this.loadState();
    return Response.json(this.state);
  }
  return new Response('Not found', { status: 404 });
}
```

## Anti-patterns

- **Embedding business logic in the router** — the router's only job is to look up
  the correct DO by key and forward the event; all logic lives in the DO.
- **Long-polling for completion** — use a WebSocket on the DO or a separate
  notification event rather than polling the `/state` endpoint in a tight loop.
- **Storing compensating commands as code, not state** — the step to compensate must
  be persisted so it survives a DO eviction between steps.
- **Catching all exceptions silently** — unhandled command failures must move the
  process to `Compensating` or `Failed`; swallowing them leaves the process stuck.

## Gotchas

- Durable Objects are evicted after ~30 s of inactivity; alarm-based timeouts survive
  eviction because alarms are persisted independently of in-memory state.
- `ctx.storage.setAlarm` replaces any existing alarm — if you need multiple timeouts
  track them in state and set the nearest one.
- Queue consumer Workers calling a DO stub must handle the case where the DO has not
  been started yet (e.g., first event arrives before `start()` is called).
- DO storage `put` is synchronous in the sense that it is committed before the handler
  returns, but a concurrent request can still see stale in-memory state if you skip
  `loadState()` at the top of each method.

## Verification

```bash
# Trigger a full happy-path flow and inspect state at each step
curl -X POST https://api.example.com/orders \
  -d '{"orderId":"ord-1","items":[{"skuId":"sku-1","qty":2}]}'

# Poll process state
curl https://api.example.com/process/ord-1/state

# Simulate payment timeout by firing alarm early (local dev only)
wrangler dev --local
curl -X POST http://localhost:8787/__scheduled?tag=alarm
```

## Related

- `process-manager-vs-saga.md`
- `saga-pattern-orchestration.md`
- `compensating-transaction-workers-saga-rollback.md`
- `durable-objects-workflow-state-machine.md`
- `durable-object-alarm-api-scheduled-retry.md`
- `parallel-saga-durable-objects-fork-join.md`

## Sources

- Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns*, Process Manager (p. 312)
- Cloudflare Durable Objects Alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Chris Richardson, *Microservices Patterns*, ch. 4 (Saga)
