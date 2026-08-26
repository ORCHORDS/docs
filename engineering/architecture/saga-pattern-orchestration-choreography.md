# Saga Pattern — Orchestration vs Choreography for Distributed Transactions

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your microservices need to coordinate a multi-step business process
(order → payment → inventory → shipping) but you cannot use a
distributed database transaction. One service completes successfully
but the next fails, leaving data inconsistent across services. You have
no mechanism to roll back the first service's changes when a downstream
step fails. Manual intervention is required to fix inconsistencies, and
debugging which step failed across 5 services takes hours.

## Context

The Saga pattern manages data consistency across microservices without
distributed transactions (2PC). A saga is a sequence of local
transactions where each step publishes an event or message triggering
the next, and each step has a compensating transaction to undo its
effects if a later step fails. In 2026, there are two implementation
styles: choreography (services react to events autonomously) and
orchestration (a central coordinator directs the flow). Most teams lean
toward orchestration for sagas with more than 3 steps, especially with
tools like Temporal, AWS Step Functions, and Azure Durable Functions
providing highly available orchestrators. Hybrid approaches — using
choreography for naturally decoupled subdomains and orchestration for
complex flows — are increasingly common.

## Choreography vs orchestration

```
Choreography:
  Each service publishes events → other services react
  No central coordinator
  Coupling: implicit (through event contracts)
  Visibility: low (flow spread across services)
  Best for: simple flows (2-3 steps), loosely coupled domains

  Order ──event──► Payment ──event──► Inventory ──event──► Shipping
    │                 │                   │                    │
    ◄──compensate─────◄──compensate───────◄──compensate────────┘

Orchestration:
  Central orchestrator sends commands → services respond
  Single point that knows the entire flow
  Coupling: explicit (orchestrator knows all steps)
  Visibility: high (flow visible in one place)
  Best for: complex flows (4+ steps), business-critical processes

                    ┌──────────────┐
                    │ Orchestrator │
                    │ (Temporal /  │
                    │ Step Fns)    │
                    └──────┬───────┘
                     ┌─────┼─────┐
                     ▼     ▼     ▼
                  Order Payment Inventory
```

## Choreography implementation

```javascript
// Order Service — publishes event after local transaction
class OrderService {
  async createOrder(orderData) {
    const order = await db.transaction(async (tx) => {
      const order = await tx.orders.create({
        ...orderData,
        status: 'PENDING',
      });

      await tx.outbox.create({
        aggregateId: order.id,
        eventType: 'OrderCreated',
        payload: JSON.stringify(order),
      });

      return order;
    });

    return order;
  }
}

// Payment Service — reacts to OrderCreated
class PaymentConsumer {
  async handleOrderCreated(event) {
    try {
      const payment = await paymentGateway.charge(event.payload);

      await db.transaction(async (tx) => {
        await tx.payments.create({ orderId: event.aggregateId, ...payment });
        await tx.outbox.create({
          aggregateId: event.aggregateId,
          eventType: 'PaymentCompleted',
          payload: JSON.stringify(payment),
        });
      });
    } catch (error) {
      await db.transaction(async (tx) => {
        await tx.outbox.create({
          aggregateId: event.aggregateId,
          eventType: 'PaymentFailed',
          payload: JSON.stringify({ reason: error.message }),
        });
      });
    }
  }
}

// Order Service — compensates on PaymentFailed
class OrderCompensator {
  async handlePaymentFailed(event) {
    await db.orders.update(
      { id: event.aggregateId },
      { status: 'CANCELLED', cancelReason: 'payment_failed' }
    );
  }
}
```

## Orchestration implementation (Temporal)

```typescript
// Saga orchestrator as a Temporal workflow
import { proxyActivities, sleep } from '@temporalio/workflow';

const { createOrder, processPayment, reserveInventory, scheduleShipping,
        cancelOrder, refundPayment, releaseInventory } =
  proxyActivities({ startToCloseTimeout: '30s', retry: { maximumAttempts: 3 } });

export async function orderSaga(orderData) {
  let orderId, paymentId, reservationId;

  try {
    orderId = await createOrder(orderData);
    paymentId = await processPayment(orderId, orderData.amount);
    reservationId = await reserveInventory(orderId, orderData.items);
    await scheduleShipping(orderId, orderData.address);

    return { status: 'completed', orderId };
  } catch (error) {
    // Compensating transactions in reverse order
    if (reservationId) await releaseInventory(reservationId);
    if (paymentId) await refundPayment(paymentId);
    if (orderId) await cancelOrder(orderId);

    return { status: 'compensated', orderId, reason: error.message };
  }
}
```

## Outbox pattern (reliable event publishing)

```
Problem: publishing an event AFTER a database commit is not atomic.
  If the app crashes between commit and publish, the event is lost.

Solution: write the event into an outbox table INSIDE the same
  database transaction. A separate process reads the outbox and
  publishes to the message broker.

┌────────────────────────────────────┐
│ Database Transaction               │
│  1. UPDATE orders SET status=...   │
│  2. INSERT INTO outbox (event)     │
│  COMMIT                            │
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│ Outbox Relay (CDC / polling)       │
│  Read outbox → publish to Kafka    │
│  Mark as published                 │
└────────────────────────────────────┘

CDC options: Debezium (PostgreSQL WAL), DynamoDB Streams
Polling: SELECT * FROM outbox WHERE published = false
```

## Decision matrix

```
                    Choreography         Orchestration
Complexity:         Low (2-3 steps)      Any (scales to 10+)
Visibility:         Low (distributed)    High (centralized)
Coupling:           Loose (events)       Tighter (commands)
Debugging:          Hard                 Easy (single log)
Compensation:       Each service owns    Orchestrator handles
Single point:       None                 Orchestrator (HA)
Testing:            Integration-heavy    Unit-testable workflow
Tooling:            Kafka, RabbitMQ      Temporal, Step Fns
Maintenance:        Hard at scale        Easier at scale

Rule of thumb:
  ≤3 steps, loosely coupled → choreography
  >3 steps or complex logic → orchestration
  Mixed domains → hybrid
```

## Anti-patterns

- **Distributed transactions disguised as sagas** — using
  two-phase commit (2PC) or distributed locks between
  microservices. Sagas embrace eventual consistency. If you need
  strong consistency, consider merging the services.
- **Missing compensating transactions** — implementing the forward
  path without implementing compensation for every step. Each
  saga step MUST have a compensating transaction defined before
  the saga goes to production.
- **Choreography spaghetti** — building a 7-step choreographed
  saga where the event chain is impossible to follow. Refactor to
  orchestration when the flow exceeds 3-4 steps or when debugging
  becomes time-consuming.
- **Ignoring the outbox pattern** — publishing events after the
  database commit without transactional outbox. This creates
  inconsistency when the application crashes between commit and
  publish.

## Gotchas

- **Idempotency is mandatory** — saga steps may be retried due to
  network failures. Every step (and every compensating transaction)
  must be idempotent. Use idempotency keys or check-before-write
  patterns.
- **Semantic rollback is not atomic rollback** — compensating
  transactions do not undo the original action atomically. A
  refund is a new transaction, not an undo of the charge. Users
  may see temporary inconsistencies between steps.
- **Orchestrator availability** — the orchestrator is a single
  point of coordination (not failure, if HA). Use durable
  orchestrators (Temporal, Step Functions) that persist workflow
  state and survive restarts.
- **Event ordering** — choreographed sagas assume events arrive
  in order. In distributed systems, events may arrive out of order.
  Use sequence numbers or timestamps to detect and handle reordering.

## Verification

- Every saga step has a defined compensating transaction.
- Outbox pattern ensures reliable event publishing.
- Saga steps and compensations are idempotent.
- Failed sagas compensate fully (no dangling state).
- Orchestrator workflows are unit-tested with mocked activities.
- End-to-end saga flow is tested with failure injection.

## Related

- `documentation/categories/architecture/event-driven-architecture.md`
- `documentation/categories/patterns/transactional-outbox-pattern.md`
- `documentation/categories/architecture/microservices-communication-patterns.md`

## Source URLs (verified 2026-08-16)

- Event-Driven Architecture: Saga Patterns, Outboxes, Distributed Consistency — https://thebackenddevelopers.substack.com/p/event-driven-architecture-saga-patterns
- Saga Pattern Demystified: Orchestration vs Choreography — https://blog.bytebytego.com/p/saga-pattern-demystified-orchestration
- Microsoft Saga Design Pattern — https://learn.microsoft.com/en-us/azure/architecture/patterns/saga
- Saga Pattern for Microservices Explained — https://www.conduktor.io/glossary/saga-pattern-for-distributed-transactions
