# Event-Driven Architecture (EDA) Overview

> **When to use:** Decoupling producers from consumers so the system can react
> to things that happen in real time (orders placed, files uploaded, sensors
> firing) without tight coupling or synchronous chains.

## Symptom

You see these signals in a request-response system that has outgrown itself:

- A single user action triggers 5+ sequential HTTP calls. Latency stacks
  linearly and one slow downstream drags the whole chain.
- Adding a new side-effect (e.g. "also send a welcome email on signup")
  requires editing the signup service and redeploying it.
- Producers and consumers are deployed together, so a crash in the email
  sender takes down signups.
- The same business event (OrderPlaced) is copy-pasted across services as
  inline logic, so they drift out of sync.
- You cannot replay the past: there is no durable record of *what happened*,
  only the current state.

If two or more of these are true, the synchronous request-response style is
creating coupling that an event-driven model would dissolve.

## Core Idea

Producers emit **events** (`OrderPlaced`, `PaymentCaptured`) to a broker
(Kafka, NATS, EventBridge, RabbitMQ, Redis Streams). Consumers subscribe and
react independently. The producer does not know—or care—who listens.

```
[Order Service] --OrderPlaced--> [Broker] --+--> [Inventory] (reserve stock)
                                            +--> [Notification] (email buyer)
                                            +--> [Analytics] (update dashboard)
```

Three topology flavors, each with a different trade-off:

| Topology | Best for | Watch out |
|---|---|---|
| **Broker** (Kafka, EventBridge) | High fan-out, event sourcing, replay | Event ordering across partitions is hard |
| **Mediator** (orchestrator like AWS Step Functions) | Multi-step workflows with control flow | Reintroduces a coordinator coupling |
| **Hybrid** | Most real systems | More moving parts to operate |

## Gotchas

- **At-least-once is the realistic guarantee.** Exactly-once is almost never
  free. Every consumer MUST be idempotent (dedupe by event id / idempotency
  key). See `idempotency-design.md`.
- **Event ordering breaks under partitioning.** Kafka guarantees order only
  within a partition. If `OrderPlaced` and `OrderCancelled` land on different
  partitions, the cancel can be processed first. Partition by the entity id
  (`orderId`) to keep related events ordered.
- **Schema evolution is a first-class concern.** Events live forever in a log.
  Without a schema registry (Avro, Protobuf, JSON Schema), a producer change
  silently breaks every consumer. Treat the event schema as a public API.
- **Poison messages loop forever.** A malformed event that crashes the
  consumer will be redelivered indefinitely. Always pair a DLQ (dead-letter
  queue) with bounded retry, not infinite retry.
- **Debugging is harder.** There is no single call stack to trace. You need
  correlation ids propagated on every event and centralized log search.
- **"Fire and forget" is a lie.** If you publish to a broker and then commit
  your DB transaction, a crash between the two loses the event. Use the
  **transactional outbox pattern** (`outbox-pattern.md`): write the event
  into an `outbox` table in the same DB transaction, then a relay publishes it.
- **Eventual consistency surprises users.** "I placed the order but inventory
  still shows it in stock for 3 seconds." Surface loading states and set
  correct expectations in the UI.
- **Fan-out storms.** One event triggering 20 consumers, each calling 3 APIs,
  creates surprise load. Rate-limit consumers independently.

## Practical Example (AWS EventBridge + Lambda)

```typescript
// Producer — inside OrderService, after committing the DB transaction
import { EventBridgeClient, PutEventsCommand } from "@aws-sdk/client-eventbridge";

const eb = new EventBridgeClient({});
await eb.send(new PutEventsCommand({
  Entries: [{
    Source: "order.service",
    DetailType: "OrderPlaced",
    Detail: JSON.stringify({
      orderId: order.id,
      customerId: order.customerId,
      total: order.total,
      eventTime: new Date().toISOString(),
    }),
  }],
}));
```

```typescript
// Consumer — Lambda, idempotent, dedupes by orderId
export const handler = async (event: EventBridgeEvent<"OrderPlaced", OrderPlaced>) => {
  const { orderId } = event.detail;
  if (await alreadyProcessed(orderId)) return; // idempotency guard
  await reserveInventory(orderId);
  await markProcessed(orderId);
};
```

## When NOT to use EDA

- **Simple CRUD with <5 services** — the operational cost of a broker is not
  worth it. A direct DB call is fine.
- **Hard real-time / synchronous requirements** (payment authorization, login).
  The user cannot wait for eventual consistency.
- **Team of one** — you will spend more time operating Kafka than shipping.

## Decision Checklist

1. Do multiple independent consumers need to react to the same event? -> EDA
2. Can consumers work off stale data (eventual consistency OK)? -> EDA
3. Do you need to replay historical events? -> EDA + event sourcing
4. Is the system request-response with one caller and one callee? -> Stay sync
5. Can you afford the operational cost of a broker + DLQ + schema registry?
   If no, start with the transactional outbox on a regular DB.

## Related Articles

- `event-sourcing-pattern.md` — storing events as the source of truth
- `outbox-pattern.md` — safely publishing events from a DB transaction
- `saga-pattern-choreography.md` — multi-step event-driven workflows
- `at-least-once-delivery.md`, `exactly-once-delivery.md` — delivery semantics
- `cqrs-pattern.md` — separating read and write models, often paired with EDA
