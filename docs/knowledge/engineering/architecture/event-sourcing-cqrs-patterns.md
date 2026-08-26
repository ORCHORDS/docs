# Event Sourcing and CQRS Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application stores only the current state in the database — when a
record changes, the previous value is overwritten. You cannot answer
"what was the state of order X at 3pm yesterday?" or "who changed field
Y and when?" without manually built audit tables that drift from reality.
Read and write performance requirements conflict: optimizing the schema
for fast writes makes complex queries slow, and vice versa.

## Context

Event Sourcing stores state changes as an immutable, append-only sequence
of events rather than overwriting the current state. CQRS (Command Query
Responsibility Segregation) separates the write model (commands) from
the read model (queries), allowing each to be optimized independently.
These patterns are often used together but are independent — you can adopt
CQRS without Event Sourcing and vice versa. In 2026, mature frameworks
(Axon, EventStoreDB, Marten) and managed event stores have lowered the
adoption barrier, though these patterns remain best applied selectively
to core domains where history, auditability, or complex domain logic
justifies the additional complexity.

## Event Sourcing fundamentals

### Events as the source of truth

```
Traditional: UPDATE orders SET status = 'shipped' WHERE id = 123
Event Sourced:
  Event 1: OrderCreated { orderId: 123, items: [...], total: $50 }
  Event 2: PaymentReceived { orderId: 123, amount: $50 }
  Event 3: OrderShipped { orderId: 123, trackingNumber: "1Z999..." }
```

The current state is derived by replaying all events in order. The event
stream is the system of record — the database row is a cache.

### Event store requirements

| Requirement | Description |
|---|---|
| Append-only | Events are never modified or deleted |
| Ordered | Events within a stream maintain insertion order |
| Optimistic concurrency | Writes check expected version to prevent conflicts |
| Subscriptions | Consumers receive new events in real time |
| Snapshots | Periodic state snapshots to avoid replaying thousands of events |

### Snapshot optimization

For aggregates with many events (thousands+), replaying from event zero
is slow. Store periodic snapshots of the computed state:

```
Events 1-1000 → Snapshot at event 1000 (full state)
Events 1001-1050 → Replay only 50 events from snapshot
```

Take snapshots every N events (e.g., every 100) or when aggregate
load time exceeds a threshold.

## CQRS fundamentals

```
                    ┌──────────────┐
  Commands ────────►│  Write Model │──── Events ────►  Event Store
                    └──────────────┘                       │
                                                           │ project
                    ┌──────────────┐                       ▼
  Queries ◄────────│  Read Model  │◄──────────────  Projections
                    └──────────────┘              (denormalized views)
```

### Projections

Projections (also called read models or materializations) consume events
and build denormalized views optimized for specific queries:

```
Event: OrderShipped { orderId: 123, trackingNumber: "1Z..." }
  → Update orders_list_view: set status = 'shipped'
  → Update shipping_dashboard: increment daily_shipments
  → Update customer_activity: add shipment record
```

One event can update multiple projections. Each projection is tailored
to a specific read use case.

### Eventual consistency

The write side and read side are eventually consistent. After a command
is processed and events are stored, projections update asynchronously.
The read model may lag by milliseconds to seconds.

## When to use (and when not to)

### Good fit

- **Audit-critical domains** — finance, healthcare, legal, where full
  history is a regulatory requirement.
- **Complex domain logic** — domains where understanding the sequence
  of state transitions matters (order management, workflow engines).
- **Temporal queries** — "what was the portfolio value at market close
  on March 15?" requires replaying events to that point.
- **Event-driven architectures** — systems already built around events
  benefit from storing events as the source of truth.

### Poor fit

- **Simple CRUD** — basic create-read-update-delete operations gain
  nothing from event sourcing. A users table that stores name and email
  does not need an event stream.
- **High-throughput, low-value writes** — logging, analytics, and IoT
  sensor data generate too many events to store individually.
- **Teams without event-driven experience** — the learning curve is
  steep. Start with CQRS (simpler) before adding event sourcing.

## Event schema evolution

Events are stored forever, making schema evolution the highest-cost
decision in event-sourced systems:

| Strategy | Description | Trade-off |
|---|---|---|
| **Upcasting** | Transform old events to new schema on read | No data migration; read-time cost |
| **Versioned events** | Store schema version with each event | Consumers handle multiple versions |
| **Copy-transform** | Migrate event store to new schema | Downtime; clean schema |
| **Weak schema** | Use flexible formats (JSON) | No migration needed; less type safety |

Best practice: design events as facts about what happened (past tense),
not commands. `OrderShipped` is a fact; `ShipOrder` is a command.

## Anti-patterns

- **Event sourcing everything** — applying event sourcing to every
  service in a microservices architecture. Apply selectively to core
  domains where history tracking provides value.
- **Large events** — storing entire aggregate state in every event
  instead of just the change. Events should contain only the delta.
- **Missing idempotency on projections** — projections must be
  idempotent because event replay is a standard operational procedure.
  Processing the same event twice must produce the same result.
- **No event versioning strategy** — adding fields to events without a
  schema evolution plan breaks consumers when old events are replayed.

## Gotchas

- **Projection rebuild time** — rebuilding projections from scratch
  (replaying all events) can take hours for large event stores. Design
  for incremental rebuilds and test rebuild procedures regularly.
- **Event ordering across aggregates** — events within one aggregate
  are ordered, but events across aggregates have no guaranteed global
  order. Use correlation IDs and causal ordering where needed.
- **GDPR and event deletion** — immutable event stores conflict with
  the right to erasure. Use crypto-shredding (encrypt personal data
  with per-user keys, delete the key to "erase") rather than deleting
  events.
- **Debugging complexity** — understanding system state requires
  replaying events rather than querying a table. Invest in tooling for
  event stream inspection and time-travel debugging.

## Verification

- Event store is append-only with optimistic concurrency control.
- Projections are idempotent and can be rebuilt from the event stream.
- Event schema evolution strategy is documented and tested.
- Snapshot frequency is tuned for aggregate load time (target: < 100ms).
- GDPR compliance uses crypto-shredding, not event deletion.
- CQRS read models handle eventual consistency gracefully in the UI.

## Related

- `documentation/docs/policies/architecture/microservices-patterns.md`
- `documentation/docs/policies/database/postgresql-optimization.md`
- `documentation/docs/policies/patterns/event-driven-architecture.md`

## Source URLs (verified 2026-08-16)

- CQRS and Event Sourcing implementation guide — https://calmops.com/architecture/cqrs-event-sourcing-practical-implementation-2026/
- Event Sourcing pattern (Microsoft) — https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
- Event Sourcing + CQRS architecture — https://www.youngju.dev/blog/architecture/2026-03-10-event-sourcing-cqrs-architecture-implementation.en
- Mia-Platform event sourcing guide — https://mia-platform.eu/blog/understanding-event-sourcing-and-cqrs-pattern/
