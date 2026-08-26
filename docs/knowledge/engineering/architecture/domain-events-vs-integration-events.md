# Domain Events vs Integration Events Patterns

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A team building a domain-driven service conflates "events" into a single concept: when an order
is placed, they publish an `OrderPlaced` event to a Kafka topic and also use the same message
inside the aggregate to trigger side effects. Six months later, the external schema of
`OrderPlaced` cannot be changed without breaking downstream consumers, internal domain logic
leaks into the public API contract, and the bounded context has no ability to refactor its
invariants without a cross-team release coordination.

The root cause is treating **domain events** (internal signals about state changes within a
bounded context) and **integration events** (public contracts published across bounded-context
or service boundaries) as the same thing.

---

## Context

**Domain events** were introduced in Eric Evans's DDD Blue Book and refined in Vaughn Vernon's
"Implementing Domain-Driven Design." They are named facts about something that happened inside
the domain model, in past tense (`OrderConfirmed`, `PaymentAuthorized`, `InventoryReserved`).
They live within the bounded context, are raised by aggregates, and carry only the information
the domain model knows at the moment the event occurs.

**Integration events** (sometimes called "public events" or "event notifications") are messages
published to external consumers — other bounded contexts, third-party webhooks, analytics
pipelines. They must maintain backward compatibility across versions, carry enough data to be
useful without requiring the consumer to call back for more, and be documented as a public API.

The two types have opposite forces:

| Dimension            | Domain Event                      | Integration Event                  |
|----------------------|-----------------------------------|------------------------------------|
| Audience             | Same bounded context              | External consumers                  |
| Lifecycle            | Short-lived (in-process or local) | Long-lived, versioned               |
| Schema stability     | Can change freely with refactoring| Must be backward-compatible        |
| Richness             | Minimal — what the aggregate knows| Sufficient for consumer autonomy   |
| Transport            | In-memory, local queue, or outbox | Message broker / webhook           |
| Authorization        | Implicit (same trust boundary)    | Explicit — consumers subscribe     |

---

## 1. Domain Events Inside the Aggregate

Domain events are raised by the aggregate root as a byproduct of state transitions. They are
consumed within the same bounded context by domain services or application handlers.

```typescript
// order/domain/events.ts
export interface DomainEvent {
  readonly occurredAt: Date;
  readonly aggregateId: string;
}

export interface OrderConfirmed extends DomainEvent {
  readonly type: 'OrderConfirmed';
  readonly totalAmountCents: number;
  readonly lineItemIds: string[];
}

export interface OrderCancelled extends DomainEvent {
  readonly type: 'OrderCancelled';
  readonly reason: string;
}

// order/domain/order-aggregate.ts
export class Order {
  private _events: DomainEvent[] = [];

  // Expose raised events for the application layer to collect
  get domainEvents(): DomainEvent[] {
    return [...this._events];
  }

  clearEvents(): void {
    this._events = [];
  }

  confirm(): void {
    if (this._status !== 'pending') {
      throw new Error(`Cannot confirm order in status ${this._status}`);
    }
    this._status = 'confirmed';
    // Raise a domain event — no external knowledge needed
    this._events.push({
      type: 'OrderConfirmed',
      occurredAt: new Date(),
      aggregateId: this._id,
      totalAmountCents: this._totalAmountCents,
      lineItemIds: this._lineItems.map((li) => li.id),
    } satisfies OrderConfirmed);
  }
}
```

The application service collects these events after saving the aggregate and dispatches them to
in-process handlers:

```typescript
// order/application/confirm-order.handler.ts
export class ConfirmOrderHandler {
  constructor(
    private readonly repo: OrderRepository,
    private readonly eventBus: DomainEventBus,
    private readonly integrationPublisher: IntegrationEventPublisher
  ) {}

  async execute(command: ConfirmOrderCommand): Promise<void> {
    const order = await this.repo.findById(command.orderId);
    order.confirm();

    await this.repo.save(order); // persist state change first

    // Dispatch domain events in-process
    for (const event of order.domainEvents) {
      await this.eventBus.publish(event);
    }
    order.clearEvents();
  }
}
```

---

## 2. Translating to Integration Events via an Anti-Corruption Layer

The **translation layer** (an application service or dedicated mapper) listens for domain events
and decides whether — and how — to publish an integration event. This is the seam where internal
domain language is mapped to the public API contract.

```typescript
// order/application/order-integration-publisher.ts
import type { OrderConfirmed } from '../domain/events';

/**
 * Integration event schema — public, versioned, consumer-facing.
 * Schema is stable across refactors of the Order aggregate.
 */
export interface OrderPlacedIntegrationEvent {
  schemaVersion: '1.2';
  eventId: string;
  occurredAt: string;        // ISO-8601
  orderId: string;
  customerId: string;        // enriched from read model — not on domain event
  totalAmountCents: number;
  currencyCode: string;      // enriched
  lineItemCount: number;
  source: 'orders-service';
}

export class OrderIntegrationPublisher {
  constructor(
    private readonly customerReadModel: CustomerReadModel,
    private readonly outbox: OutboxRepository,
    private readonly idGenerator: IdGenerator
  ) {}

  @DomainEventHandler(OrderConfirmed)
  async onOrderConfirmed(event: OrderConfirmed): Promise<void> {
    // Enrich: fetch customer data that the Order aggregate does not own
    const customer = await this.customerReadModel.findByOrderId(event.aggregateId);

    const integrationEvent: OrderPlacedIntegrationEvent = {
      schemaVersion: '1.2',
      eventId: this.idGenerator.generate(),
      occurredAt: event.occurredAt.toISOString(),
      orderId: event.aggregateId,
      customerId: customer.id,
      totalAmountCents: event.totalAmountCents,
      currencyCode: customer.preferredCurrency,
      lineItemCount: event.lineItemIds.length,
      source: 'orders-service',
    };

    // Write to outbox (same transaction as the domain write)
    await this.outbox.store({
      destination: 'order.placed',
      payload: integrationEvent,
    });
  }
}
```

Key rule: the domain event contains only what the aggregate knows. The integration event contains
what consumers need — enriched with data from read models, cross-context lookups, and formatted
for external compatibility.

---

## 3. Versioning Integration Events Without Touching Domain Events

Integration events need semantic versioning and backward-compatible evolution. Domain events do not
— they are free to change because no external consumer depends on them.

```typescript
// Versioning strategy: parallel schemas with a version discriminator
export type OrderPlacedEvent =
  | OrderPlacedV1
  | OrderPlacedV2;

export interface OrderPlacedV1 {
  schemaVersion: '1.0';
  orderId: string;
  totalAmountCents: number;
}

export interface OrderPlacedV2 {
  schemaVersion: '2.0';
  orderId: string;
  totalAmountCents: number;
  currencyCode: string;      // new in v2
  customerId: string;        // new in v2 — was enriched by consumer from v1
}

// Consumer handles both versions with a type guard
function handleOrderPlaced(event: OrderPlacedEvent): void {
  if (event.schemaVersion === '2.0') {
    // v2 path — use richer data
    processWithCurrency(event.orderId, event.totalAmountCents, event.currencyCode);
  } else {
    // v1 backward-compat path
    processWithCurrency(event.orderId, event.totalAmountCents, 'USD'); // default
  }
}
```

In Cloudflare Workers, the publisher Worker writes to a Cloudflare Queue; the consumer Worker
deserialises and type-narrows on `schemaVersion`:

```typescript
// integration-event-consumer/src/index.ts
export default {
  async queue(batch: MessageBatch<OrderPlacedEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;
      // narrow by version
      if (event.schemaVersion === '2.0') {
        await handleV2(event, env);
      } else if (event.schemaVersion === '1.0') {
        await handleV1(event, env);
      } else {
        // unknown version — dead-letter
        console.error('Unknown schema version:', (event as { schemaVersion: string }).schemaVersion);
        msg.retry({ delaySeconds: 0 });
      }
      msg.ack();
    }
  },
};
```

---

## 4. Outbox Pattern — Publishing Integration Events Atomically

The outbox pattern ensures that domain state changes and integration event publication are atomic.
Write both to the same database transaction; a relay process reads the outbox and publishes to the
broker. This prevents "ghost events" (event published, then DB write fails) and "silent failures"
(DB write succeeds, event never published).

```typescript
// Pseudocode for D1-based outbox relay (Cloudflare Workers Cron)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const unpublished = await env.DB.prepare(
      `SELECT id, destination, payload FROM outbox
       WHERE published_at IS NULL
       ORDER BY created_at ASC
       LIMIT 100`
    ).all<OutboxRow>();

    for (const row of unpublished.results) {
      const payload = JSON.parse(row.payload);
      await env.INTEGRATION_QUEUE.send({ destination: row.destination, payload });
      await env.DB.prepare(
        `UPDATE outbox SET published_at = ? WHERE id = ?`
      ).bind(new Date().toISOString(), row.id).run();
    }
  },
};
```

The application service writes the domain state and the outbox entry in a single D1 transaction:

```typescript
await env.DB.batch([
  env.DB.prepare(`UPDATE orders SET status = 'confirmed' WHERE id = ?`).bind(orderId),
  env.DB.prepare(`INSERT INTO outbox (id, destination, payload) VALUES (?, ?, ?)`).bind(
    crypto.randomUUID(),
    'order.placed',
    JSON.stringify(integrationEvent)
  ),
]);
```

---

## Anti-patterns

- **Publishing domain events directly to external queues.** Leaks aggregate internals into a
  public API. Every internal refactor becomes a breaking change for consumers.
- **Embedding cross-context references in domain events.** If `OrderConfirmed` contains
  `customerId`, the Order aggregate has taken an implicit dependency on the Customer context.
  Keep domain events context-local; enrich during translation.
- **Using integration events for in-process coordination.** Round-tripping through a broker for
  same-process side effects adds latency and coupling. Use an in-memory event bus for domain event
  dispatch and reserve the broker for cross-context integration.
- **No `schemaVersion` field on integration events.** When a new field is added, consumers have
  no way to distinguish old payloads from new. Always version from the first event you publish.
- **Conflating event time with processing time.** Integration events should carry `occurredAt`
  (when the domain fact happened) separately from `publishedAt` (when it was placed on the
  broker). Consumers care about business time, not infrastructure time.

---

## Gotchas

- **Enrichment read-model lag.** If the integration publisher reads from a CQRS read model to
  enrich the event, and that read model is eventually consistent, the enriched data may be stale.
  Options: enrich synchronously from the write model (adds coupling) or accept eventual
  consistency in the integration event (document the guarantee explicitly).
- **Ordering guarantees differ.** Domain events within a single aggregate confirm happen in causal
  order by definition. Integration events on a partitioned queue (Kafka, Cloudflare Queues) only
  guarantee order within a partition. Partition by aggregate ID to preserve causal order for a
  single entity.
- **Deduplication at both layers.** Domain events can be dispatched multiple times if the
  application crashes between "save aggregate" and "clear events." Integration events can be
  re-published if the outbox relay crashes mid-batch. Both consumers should implement idempotency
  using `eventId`.

---

## Verification

```bash
# Confirm domain events are not leaking into the integration queue
# (check that integration event schema contains no aggregate internals)
wrangler queues consumer get --queue integration-events | jq '.messages[0].body | keys'

# Verify outbox is draining (no rows older than 30 seconds unpublished)
wrangler d1 execute orders-db \
  --command "SELECT count(*) as stuck FROM outbox WHERE published_at IS NULL AND created_at < datetime('now', '-30 seconds')"

# Schema version distribution on integration queue
wrangler queues consumer get --queue integration-events \
  | jq '[.messages[].body.schemaVersion] | group_by(.) | map({version: .[0], count: length})'
```

---

## Related

- `domain-events.md`
- `outbox-pattern.md`
- `event-schema-versioning.md`
- `bounded-context-design.md`
- `anti-corruption-layer.md`
- `cqrs-cloudflare-workers-d1.md`

---

## Sources

- Evans, Eric. *Domain-Driven Design: Tackling Complexity in the Heart of Software.* Addison-Wesley, 2003.
- Vernon, Vaughn. *Implementing Domain-Driven Design.* Addison-Wesley, 2013. Chapter 8: Domain Events.
- Richardson, Chris. "Pattern: Transactional outbox." microservices.io/patterns/data/transactional-outbox.html
- Stam, Kees. "Domain Events vs Integration Events." https://medium.com/@keesanstam
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Fowler, Martin. "What do you mean by 'Event-Driven'?" martinfowler.com/articles/201701-event-driven.html
