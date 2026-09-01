# Cqrs Read Model Projection Event Ordering

## Scope

This article addresses the engineering problem of building read-model projections from a stream of domain events in a CQRS architecture. It explains why event ordering matters for projection correctness, how ordering is established by the event store, how it is preserved across handlers, and how it is recovered when it is lost. The discussion covers single-stream ordering, global ordering, partitioned ordering, out-of-order delivery, idempotent projection, and the role of sequence numbers and version stamps. The article applies to any CQRS or event-sourced system, including those implemented on Cloudflare Workers with Durable Objects and queues, on Kafka, on EventStoreDB, or on a relational outbox.

## Workflow or implementation guidance

A projection is a function from a sequence of events to a read model. The projection consumes events in some order, applies each event to the current state of the read model, and writes the result. The correctness of the projection depends on the order in which events are applied: applying "OrderShipped" before "OrderPlaced" produces an incoherent state. Ordering therefore begins at the source.

In an event-sourced system, each aggregate (each order, each account, each invoice) has its own stream of events, and the event store guarantees that events within a stream are appended in the order in which they were raised. This is single-stream ordering, and it is sufficient for many projections: as long as the projection consumes the stream in order, the read model is correct. The difficulty arises when the projection consumes events from multiple streams, or when the projection is itself distributed across multiple workers.

The first step in implementation is to choose the ordering guarantee. Three guarantees are commonly needed: ordering within a stream (always), ordering within a partition key (common), and global ordering across all streams (rare and expensive). Global ordering requires a single consumer, which destroys parallelism and therefore scalability. Partitioned ordering—grouping events by aggregate ID, tenant ID, or some other key—allows many parallel consumers while preserving the order within each group. The second step is to attach a sequence number or version to each event as it is appended. The event store assigns a monotonically increasing number per stream; this becomes the basis for "have I seen this event?" and "where should I resume?".

The third step is to design the consumer for out-of-order delivery. Even with the best guarantees, a consumer can be restarted between two events, or a rebalance can split a partition. The projection must be able to handle an event arriving out of order without corrupting state. The standard technique is to store the projection's checkpoint per stream (the last applied event version) and to refuse to apply an event with a version less than or equal to the checkpoint. The fourth step is to make the projection idempotent. An event delivered twice—because the consumer crashed after applying it but before checkpointing—must not double-apply. This is typically achieved by storing the event ID in the read model and rejecting duplicates.

The fifth step is to handle replays. When a new projection is added, or an existing projection is rebuilt from scratch, the consumer must read the entire event history in order and rebuild the read model. This is the operation that makes the architecture worth its complexity: the read model is derived, and any inconsistency can be healed by replay. The catch is that the replay must be correctly ordered, or the rebuilt read model will be wrong. The standard safeguard is to build the new read model into a separate store, validate it against the old, then cut over.

## Controls

The projection must enforce three controls: in-order consumption, idempotent application, and checkpointing. In-order consumption is enforced at the consumer side by refusing to apply an event whose version is less than the checkpoint, and at the producer side by serialising appends per stream. Idempotent application is enforced by storing the event ID inside the read model and rejecting duplicates. Checkpointing is enforced by writing the new checkpoint transactionally with the read-model update.

A second class of controls covers the read-model side. The read model must be queryable, indexable, and consistent with the projection's notion of completeness. A "projection lag" metric (the difference between the latest event in the store and the latest event applied to the read model) must be observable in real time. A lag that grows unboundedly is a signal that the projection is falling behind or has stalled.

A third class of controls covers the event schema. If the event schema changes, the projection must be updated or replayed; the schema registry and the projection's compatibility settings must be aligned so that a forward-incompatible change cannot be deployed without a migration plan.

## Validation evidence

Validation must prove three things. First, that a single stream of events applied in order produces a correct read model. This is the easy case and is verified by replaying a known stream and asserting the resulting state. Second, that out-of-order events are rejected. The test replays events with deliberate reordering and asserts that the projection refuses to apply the late event. Third, that replays reproduce the same read model bit-for-bit. The test writes a stream, projects it, then rebuilds the projection from scratch and asserts that the two read models match.

Validation must also prove the recovery path. A consumer is killed between two events; on restart, it resumes from the checkpoint and does not lose or duplicate events. The test must be repeated for crashes at every interesting point (after the read-model update, before the checkpoint; after the checkpoint, before the acknowledgement) and the system must be correct in each case.

## Failure modes and correction

The dominant failure mode is applying events out of order across aggregates. Two consumers in the same partition both think they own the partition; they both apply events; the read model ends up with one consumer's events applied in a different order than the other intended. The cure is exclusive ownership of partitions (one consumer per partition at a time) and rebalance with sticky assignment. A second failure mode is the projection falling behind because of a slow downstream. The cure is to back-pressure: stop polling the event store, allow the queue to build, and respond with an explicit "lagging" signal to clients that read through the projection.

A third failure mode is duplicate application. The consumer crashes after writing the read model but before checkpointing; on restart it reads the event again and applies it twice. The cure is idempotent application: the read-model update is keyed on the event ID and rejects duplicates. A fourth failure mode is checkpoint drift. The checkpoint is stored in a system whose clock or leader is different from the read model's; the checkpoint advances even though the read model is not yet consistent. The cure is to make the checkpoint and the read-model update a single transactional operation, or to use a write-ahead log inside the consumer that is replayable.

A fifth failure mode is schema drift. An event is added or changed in a way that the projection does not understand. The cure is a schema registry with compatibility policy enforced at deployment, and a versioning strategy that allows the projection to be rebuilt.

## Limitations

Projection correctness depends on the event store's guarantees. A weak event store can produce gaps, duplicates, or reorderings that the projection cannot detect, and the read model will silently diverge from the system of record. The replay path is also expensive: rebuilding a large read model from the entire event history can take hours, and the system must accept the cost or partition the read model so that it can be rebuilt in segments. Finally, ordering and parallelism are in tension: the stronger the ordering guarantee, the fewer the consumers that can run in parallel, and the smaller the throughput. The right ordering guarantee is the weakest one that the projection's correctness requires, not the strongest one the platform offers.

## Canonical sources

- Eric Evans — *Domain-Driven Design* (the "Blue Book"), chapter on domain events and the basis for CQRS event semantics
- Martin Fowler — *CQRS* bliki entry, defining the read/write split and the role of projections: https://martinfowler.com/bliki/CQRS.html
- Greg Young — talks and writings on CQRS and event sourcing, origin of the per-stream sequence-number convention and projection idempotency rules
- Microsoft Azure Architecture Center — *CQRS pattern*, including projection guidance: https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs
