# Event-Driven and Async API Testing Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your system uses event-driven architecture — Kafka, RabbitMQ, SQS, NATS,
or similar message brokers — and your test suite only covers synchronous
request-response endpoints. Bugs in event production, consumption,
ordering, idempotency, and dead-letter handling ship to production because
the feedback loop does not exercise asynchronous paths.

## Context

Event-driven architectures require testing strategies that account for
asynchrony, eventual consistency, message ordering, concurrency, and
failure modes that do not exist in synchronous systems. Common failures —
duplicate processing, out-of-order events, silent data loss, schema
incompatibilities — are preventable with systematic testing, but they
require purpose-built test infrastructure: real brokers via Testcontainers,
polling assertions for eventual consistency, explicit idempotency
validation, and dead-letter queue verification.

## Testing layers

### Layer 1: Event production testing

Validates that a service publishes the correct events in response to
commands or state changes.

```typescript
// Vitest + Testcontainers Kafka
test('order placement publishes OrderCreated event', async () => {
  const order = await orderService.place({ items, customer });

  const events = await kafkaConsumer.waitForMessages({
    topic: 'orders.created',
    count: 1,
    timeout: 5_000,
  });

  expect(events[0].value).toMatchObject({
    orderId: order.id,
    customerId: customer.id,
    items: expect.arrayContaining([
      expect.objectContaining({ sku: items[0].sku }),
    ]),
  });
});
```

### Layer 2: Event consumption testing

Validates that a consumer correctly processes incoming events, including
idempotent handling of duplicates.

```typescript
test('payment consumer is idempotent', async () => {
  const event = buildOrderCreatedEvent({ orderId: 'order-123' });

  await paymentConsumer.handle(event);
  await paymentConsumer.handle(event); // duplicate

  const payments = await db.payments.findAll({
    where: { orderId: 'order-123' },
  });
  expect(payments).toHaveLength(1); // not 2
});
```

### Layer 3: Contract testing

Validates that producers and consumers agree on event schemas. AsyncAPI
enables contract testing between producers and consumers, ensuring both
sides remain synchronized with the specification.

```yaml
# AsyncAPI contract definition
asyncapi: 3.0.0
info:
  title: Order Service
  version: 1.0.0
channels:
  orders/created:
    messages:
      OrderCreated:
        payload:
          type: object
          required: [orderId, customerId, createdAt]
          properties:
            orderId: { type: string, format: uuid }
            customerId: { type: string }
            createdAt: { type: string, format: date-time }
```

### Layer 4: Ordering and sequencing tests

Validates that the system handles out-of-order events correctly.

```typescript
test('handles out-of-order status updates', async () => {
  await consumer.handle(statusEvent('shipped', timestamp: t2));
  await consumer.handle(statusEvent('confirmed', timestamp: t1));

  const order = await db.orders.findById(orderId);
  expect(order.status).toBe('shipped'); // latest by timestamp, not arrival
});
```

### Layer 5: Dead-letter queue (DLQ) testing

Validates that poison messages (unparseable, schema-violating, or
repeatedly failing events) are routed to the DLQ without blocking the
consumer.

```typescript
test('poison message goes to DLQ after 3 retries', async () => {
  await producer.send('orders.created', { invalid: 'payload' });

  await waitFor(async () => {
    const dlqMessages = await dlqConsumer.getMessages('orders.created.dlq');
    expect(dlqMessages).toHaveLength(1);
  }, { timeout: 30_000 });
});
```

## Test infrastructure

### Testcontainers for real brokers

Use Testcontainers to spin up real Kafka, RabbitMQ, or Redis instances
during tests. In-memory fakes miss broker-specific behavior (rebalancing,
consumer groups, partition assignment).

```typescript
import { KafkaContainer } from '@testcontainers/kafka';

const kafka = await new KafkaContainer()
  .withExposedPorts(9093)
  .start();
```

### Polling assertions for eventual consistency

Replace `expect(result).toBe(value)` with polling assertions that retry
until a condition is met or a timeout expires:

```typescript
async function waitFor(fn, { timeout = 5000, interval = 100 }) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try { await fn(); return; }
    catch { await new Promise(r => setTimeout(r, interval)); }
  }
  await fn(); // final attempt — throw the real error
}
```

## Anti-patterns

- **Mocking the broker** — in-memory mocks miss partition rebalancing,
  consumer group coordination, delivery guarantees, and serialization.
  Use Testcontainers for integration tests.
- **Fixed `sleep()` instead of polling** — `await sleep(2000)` makes
  tests slow when they pass and flaky when they fail. Use polling
  assertions with timeouts.
- **Testing only the happy path** — event-driven systems fail in unique
  ways: duplicate delivery, out-of-order arrival, partial failures,
  deserialization errors. Test each failure mode explicitly.
- **No schema evolution testing** — test that consumers handle both v1
  and v2 of an event schema. Schema evolution without consumer
  compatibility testing causes production failures.

## Gotchas

- **Testcontainers startup time** — Kafka containers take 15-30 seconds
  to start. Share the container across tests in the same suite using
  `beforeAll` and a module-level variable.
- **Consumer group rebalancing** — in tests with multiple consumers,
  rebalancing can cause messages to be delivered to unexpected consumers.
  Use unique consumer group IDs per test.
- **Transaction boundaries** — events published inside a database
  transaction may not be visible to consumers until the transaction
  commits. Test the transactional outbox pattern if you use one.
- **Clock skew** — tests that depend on event timestamps for ordering
  must control the clock. Inject a clock abstraction rather than relying
  on `Date.now()`.

## Verification

- Event production tests run on every PR for all event-producing services.
- Idempotency tests verify duplicate handling for all consumers.
- AsyncAPI contracts are validated in CI — breaking schema changes fail
  the build.
- DLQ routing is tested for each consumer.
- Testcontainers are used for all broker-dependent integration tests.
- Polling assertions are used instead of fixed sleeps.

## Related

- `documentation/categories/testing/test-pyramid-strategy.md`
- `documentation/categories/testing/model-based-testing-mbt.md`
- `documentation/categories/architecture/event-driven-architecture.md`

## Source URLs (verified 2026-08-16)

- Testing Event-Driven Microservices — https://totalshiftleft.ai/blog/testing-event-driven-microservices
- AsyncAPI Testing — https://intent-driven.dev/knowledge/asyncapi-event-driven/
- Event-Driven Testing — https://oneuptime.com/blog/post/2026-01-25-event-driven-testing/view
- TestRail Event-Driven Testing — https://www.testrail.com/blog/event-driven-application-architectures/
