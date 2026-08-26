# Event Sourcing — Projections, Snapshots, and Event Versioning

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your order management system stores only current state — when a
customer disputes a charge, you cannot prove the sequence of events
that led to the final price. An audit reveals that a discount was
applied twice, but the database only shows the current total with no
history of how it got there. Separately, your aggregate replay takes
8 seconds for a customer with 50,000 events, and your read model
rebuild after a schema change takes 6 hours because it replays every
event from the beginning.

## Context

Event sourcing persists every state change as an immutable, append-
only domain event rather than overwriting current state. Combined with
CQRS (Command Query Responsibility Segregation), it enables full audit
trails, time-travel debugging, and independently scalable read models.
By 2026, the pattern has matured with established tooling (Marten,
EventStoreDB, Axon) but remains best applied selectively to domains
where history tracking is a core requirement — finance, order
management, logistics — not as a top-level architecture for an entire
system.

## Event store design

```
Event record structure:
  aggregate_id:     UUID identifying the entity
  sequence_number:  Monotonically increasing per aggregate
  event_type:       e.g., "OrderPlaced", "ItemAdded"
  event_data:       JSON payload (the facts that happened)
  metadata:         correlation_id, causation_id, user_id, timestamp
  timestamp:        When the event was recorded

Guarantees:
  → Append-only (events are never modified or deleted)
  → Ordering within an aggregate stream is guaranteed
  → Global ordering across streams is optional (depends on store)

Architecture:
  Command → Command Handler → Event Store (write side)
                                   |
                             Event Bus / Subscription
                                   |
                             Projections → Read DB (query side)
```

## Projection patterns

```
Projections subscribe to event streams and materialize
purpose-specific read models:

  Event stream:  OrderPlaced → ItemAdded → ItemRemoved → OrderShipped
                      ↓              ↓            ↓             ↓
  Order summary:  [created]    [+item]      [-item]      [shipped]
  Revenue report: [+revenue]   [+line]      [-line]      [finalized]
  Search index:   [indexed]    [updated]    [updated]    [updated]

Rules:
  → Multiple projections from the same stream for different queries
  → Each projection is independently deployable and rebuildable
  → Projections MUST be idempotent (replaying events cannot double-count)
  → Track last processed sequence_number per projection

Blue-green projection rebuild:
  1. Build new projection into a separate table
  2. Replay all events into the new table
  3. Swap read traffic atomically (rename or switch connection)
  4. Drop old table
  → Zero downtime during schema changes
```

## Snapshot optimization

```
Problem: replaying 50,000 events to rehydrate an aggregate is slow

Solution: snapshots serialize aggregate state at a point in time
  → Load latest snapshot
  → Replay only events after the snapshot's sequence_number

Strategies:
  Every N events:    Snapshot every 100-1000 events (most common)
  Time-based:        Snapshot hourly or daily
  On-demand:         Snapshot when replay time exceeds threshold
  Adaptive:          Increase frequency for hot aggregates

Implementation:
  1. Store snapshot as: {aggregate_id, sequence_number, state_blob}
  2. On load: fetch latest snapshot, then events after its sequence
  3. Apply events on top of snapshot state

Rule: snapshots are an optimization, not a requirement.
Start without them. Add when replay latency is measured and painful.
```

## Event versioning and upcasting

```
Events are immutable but schemas evolve:

Approach 1: Weak schema (recommended)
  Use Protobuf/Avro that tolerate added/removed fields
  New fields get defaults; removed fields are ignored

Approach 2: Versioned event types
  OrderPlaced_v1 → OrderPlaced_v2
  Register upcasters that transform v1 → v2 during deserialization
  Chain upcasters: v1 → v2 → v3 (app code handles only v3)

Approach 3: Copy-and-transform (last resort)
  Migrate entire stream to new format
  Breaks immutability — use only when other approaches fail

Rules:
  → Never change the meaning of an existing event field
  → Add new fields with defaults; never remove required fields
  → Serialize primitives in events, not value objects
    (value object definitions may change; primitives are stable)
```

## Anti-patterns

- **Applying event sourcing everywhere** — use selectively in bounded
  contexts where audit/history is a core requirement. Most CRUD
  domains do not benefit from the added complexity.
- **Poor event schema design** — events persist forever. Invest
  heavily in event design upfront because schema changes are the
  highest-cost operation in an event-sourced system.
- **Non-idempotent projections** — projection rebuilds will double-
  count, corrupt read models, and require manual intervention. Always
  design projections to handle duplicate events safely.
- **Missing process managers** — many services directly subscribing
  to each other's events without coordination makes the system
  impossible to reason about. Use sagas or process managers for
  cross-aggregate workflows.

## Gotchas

- **Kafka as event store** — Kafka can distribute events but is not
  a purpose-built event store. Reconstructing aggregates from Kafka
  topics with millions of events does not scale. Keep aggregate state
  in a database and use Kafka for distribution.
- **Event ordering across aggregates** — global ordering is expensive
  and usually unnecessary. Design for eventual consistency between
  aggregates and guarantee ordering only within a single aggregate.
- **Projection lag** — read models are eventually consistent. Design
  the UI to handle this (optimistic updates, "processing" states)
  rather than forcing synchronous projection updates.
- **Event store growth** — append-only stores grow indefinitely.
  Plan for archival strategies (move old events to cold storage)
  and ensure snapshots reduce the working set.

## Verification

- Events are immutable once written (no update/delete operations).
- Projections are idempotent and track last processed sequence.
- Snapshot strategy is in place for aggregates with >1000 events.
- Event versioning uses upcasters, not mutation.
- Read model rebuild completes within acceptable time window.
- CQRS separation is clean (commands never query read models).

## Related

- `documentation/docs/policies/architecture/event-sourcing-cqrs-patterns.md`
- `documentation/docs/policies/architecture/saga-pattern-orchestration-choreography.md`
- `documentation/docs/policies/patterns/outbox-pattern-reliable-messaging.md`

## Source URLs (verified 2026-08-16)

- CQRS and Event Sourcing: Practical Implementation Patterns 2026 — https://calmops.com/architecture/cqrs-event-sourcing-practical-implementation-2026/
- Event Sourcing Production Anti-Patterns — https://www.youngju.dev/blog/architecture/2026-03-07-architecture-event-sourcing-cqrs-production-patterns.en
- Simple Patterns for Events Schema Versioning — https://event-driven.io/en/simple_events_versioning_patterns/
- Event Sourcing Pattern — Azure Architecture Center — https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
