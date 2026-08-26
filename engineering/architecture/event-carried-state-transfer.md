# event-carried-state-transfer

**Issue:** In an event-driven system, the naive way for a consumer to react to an OrderCreated event is to call back to the order service for the order details — which reintroduces the synchronous coupling and availability dependency the events were supposed to remove. Event-Carried State Transfer (ECST), articulated in Martin Fowler's "What do you mean by 'Event-Driven'," solves this by putting the entity's state in the event payload itself, so consumers maintain a local replica of the data they need and never call the producer. The payoff is genuine independence: the consumer works even when the producer is down, and read latency drops to a local lookup. The cost is what every ECST article (Vinsguru, ITNext, Fowler) warns about: eventual consistency in the consumer's replica, data duplication across services, larger event payloads, and an implicit schema contract that couples producer and consumer more tightly than a thin notification would. Teams adopt ECST for resilience and then discover they have signed up to operate a replication pipeline with correctness requirements.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Pattern

1. **Fat events.** Instead of OrderCreated(orderId), publish OrderCreated(orderId, customerName, total, currency, status, items...). The event is self-contained; any consumer that needs order context stores what it needs from the payload.
2. **Local replica per consumer.** Each consuming service keeps its own projection of the producer's entities (a read model table keyed by entity id). Reads that used to be cross-service calls become local queries against the replica.
3. **No call-backs in the happy path.** The defining property per Fowler's formulation: consumers no longer need to contact the source system for information about the entity. If a consumer must call the producer on every event to do its work, you have event notification, not ECST.
4. **Producer remains the source of truth.** The replica is a cache-like copy with defined staleness, not an authority. Writes to the entity still go to the owning service, which emits updated state as new events.

## Benefits

1. **Availability isolation.** The consumer keeps serving reads and doing its job during producer outages; ITNext and Medium treatments of ECST describe this as bringing data closer to where it is used. Degradation is bounded to freshness, not correctness of existing data.
2. **Latency and load reduction.** Local reads replace network hops; the producer sheds read traffic it was only serving for other services' benefit. This is the architectural engine behind many CQRS-style read models across service boundaries.
3. **Reduced temporal coupling.** Consumers can be down and catch up from the event log when they return, applying events at their own pace instead of being on the producer's critical path.
4. **Audit trail as a byproduct.** Because the state arrives as events, the consumer can reconstruct its replica's history — useful for debugging "why did the fulfillment service think the address was X."

## Costs and Risks

1. **Eventual consistency is the core tradeoff.** Vinsguru's summary is the standard one: you trade strong consistency for the resilient design. Every feature built on the replica must tolerate staleness — the classic bug is showing the user their new data before the replica has it (read-your-writes violation across services).
2. **Payload bloat and schema coupling.** Including state couples consumers to producer internals: adding a field helps, but renaming, restructuring, or reinterpreting an existing field breaks every replica. The event schema becomes a public API requiring the same versioning discipline as REST contracts (see event-schema-versioning in this KB).
3. **Storage duplication.** Every consumer pays storage and indexing costs for the subset of state it keeps. Duplicated data also invites the temptation to write to it, which forks the truth.
4. **Leakage of confidential fields.** Fat events broadcast data to every subscriber, including fields some consumers should never see. Either publish field-filtered variants per audience or keep sensitive fields out of the event and accept the call-back for those specific reads.
5. **Stale-data decisions.** Downstream automation (emails, payments, provisioning) acting on a stale replica is worse than a stale UI because it takes effect in the real world. Actions with irreversible effects should verify against the source, or consumers should wait for convergence on the relevant entity.

## Design Rules

1. **Plan for replay and rebuild.** Events must be retained (log or archive) so any consumer can rebuild its replica from scratch. If you cannot rebuild a projection, the replica is not a derived cache — it is unbacked state you will eventually lose.
2. **Idempotent apply with ordering guarantees.** At-least-once delivery means duplicate events; partitions or sequencers must give per-entity ordering. Apply events idempotently, keyed by entity id plus a monotonic version or timestamp, and ignore regressions (an older update arriving after a newer one).
3. **Tombstones for deletes.** Deletion must be communicated as an explicit event carrying the id, not inferred from absence. Replicas that never learn about deletes accumulate ghosts.
4. **Version the payload explicitly.** Carry a schema version in every event and evolve additively; the producer should support at least one old version during consumer migration windows.
5. **Reconciliation job.** Periodically compare replica contents against the source (counts, checksums, sampled rows) to detect dropped or misapplied events. This is the quiet difference between a self-healing projection and a slowly rotting one.
6. **Measure replica lag.** Track event publish time to apply time per consumer. Lag is your SLA for "how wrong can the replica be," and it should be visible on the same dashboard as queue depth.

## ECST vs Adjacent Patterns

1. **ECST vs event notification.** Notification events say "something changed, come look" and preserve producer-centric coupling; ECST events say "here is the new state." Notification keeps data in one place; ECST trades duplication for independence. Choose per-relationship, not globally.
2. **ECST vs event sourcing.** Event sourcing makes events the write-side source of truth inside a service's own boundary; ECST copies state across boundaries for reads. A service can event-source internally and use ECST to inform neighbors — the two compose, they do not compete.
3. **ECST vs CQRS materialized views.** The mechanics are similar (apply events to a projection); the difference is scope. Within one bounded context it is CQRS read-model maintenance; across ownership boundaries with independent deployability it is ECST, and it inherits all the cross-contract versioning obligations.
