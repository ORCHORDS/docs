# CQRS Pattern Event Store Segregation

## Scope

This article covers Command Query Responsibility Segregation with an event store as the write-side system of record: commands mutate an append-only event log, queries are served from projections built by consuming that log, and the two sides are segregated in model, storage, and scaling. Scope includes the segregation boundary, projection construction and rebuild, consistency management between write and read sides, and versioning the command and event contracts. It excludes CQRS over a single relational database with separate read models (no event store), and it excludes event sourcing as a full architectural style discussion except where the event store forces specific CQRS consequences.

## Workflow or implementation guidance

Segregate in three layers, not one. Model segregation: the command side speaks in commands and aggregates — nouns with invariants, no query methods beyond identity; the query side speaks in read shapes shaped exactly like the screens and reports consuming them. Storage segregation: the command side appends immutable events; the query side owns denormalized projection tables it may rebuild from scratch at any time. Scaling segregation: the two sides deploy, scale, and fail independently, because their load profiles are unrelated — one write can fan out to a dozen projections, and a marketing report can hammer reads without a single command.

Build projections as pure functions of event streams. Each projection declares which event types it consumes and a fold from (current state, event) to next state; the fold must be deterministic and free of side effects other than its own state write, because rebuild correctness depends on it. Handle out-of-order and duplicate delivery explicitly: checkpoint the consumer per projection per partition, key events by aggregate id plus version so replays and races are detectable, and make the fold idempotent on event id. A typical shape:

```ts
function foldBooking(state: BookingView | null, e: Event): BookingView {
  switch (e.type) {
    case 'BookingPlaced':  return { ...project(e), version: e.version };
    case 'BookingMoved':   return { ...state!, slot: e.slot, version: e.version };
    default:               return assertNever(e.type); // unknown event = loud failure
  }
}
```

Manage read-side freshness as a product decision per projection: interactive projections need sub-second lag and thus near-real-time consumption; analytics projections can batch hourly. Expose staleness to the consumer where it matters — read-your-writes for the initiating user is usually implemented by pinning that user's reads to a projection checkpoint at or beyond their command's append position, not by making everything synchronous.

Version event contracts from the start. New consumers must tolerate old events forever (or until a declared retention boundary), so prefer additive evolution: new event types, new optional fields, and upcasting functions that translate old versions to current internal representations on read. The event store is the one schema you cannot migrate in place.

## Controls

Segregation only pays if the boundary stays clean, so control it structurally. Forbid the query side from reading the event store for ad-hoc aggregation: projections are the only bridge, enforced by access policy and a code-review rule; every bypass becomes an undocumented coupling that breaks at the worst moment. Require every projection to declare its rebuild strategy (from-scratch, incremental-from-checkpoint, shadow) and its freshness SLO, and run a scheduled rebuild of one projection per week in production to prove rebuildability — a projection that cannot be rebuilt is not a projection, it is the real system of record wearing a disguise. Track per-projection lag as a first-class metric with alerts at SLO breach. Gating control: a command's acceptance must be decided by the write side's own invariants, never by querying a projection, because projection lag then becomes a correctness bug (two users booking the last seat through a stale read). If business rules require cross-aggregate views, implement them as a process manager consuming events, not as a command-time projection lookup.

## Validation evidence

The decisive evidence is rebuild equivalence. Periodically rebuild each projection from the event store and diff the result against the live projection, record by record; the diff must be empty or explained by documented in-flight window effects. This single test catches the entire class of nondeterministic-fold bugs — accidental wall-clock calls, random ids, unordered map iteration — which are invisible in forward operation and fatal during recovery. Fault-injection on the consumption path: deliver a duplicate event, an out-of-order event, and a truncated stream to a projection in staging and assert convergence to the correct state after redelivery. Freshness evidence: measure command-append to projection-visibility lag per projection under production-shaped load, charting the distribution rather than the mean. Contract tests: for every command, assert the resulting event sequence and for every event type, assert each consuming projection's fold output — these tables double as living documentation of what the segregation actually guarantees. Finally, exercise the read-your-writes path with a concurrency test: command and immediate read from two connections, asserting the read observes the write under the pinning mechanism.

## Failure modes and correction

The most common failure is projection rot: a fold bug ships, the projection accumulates wrong state, and because it cannot be rebuilt correctly the team patches rows by hand. Correct by making the weekly production rebuild mandatory and by treating any manual row edit on a projection as an incident with a postmortem — the rebuild discipline is the pattern's immune system. The second is invariant enforcement on stale reads: a command gated on projection state admits what the invariants should have forbidden, because the projection lagged. Correct by moving the invariant to the aggregate or a process manager as described under Controls. The third is event contract drift: a team renames an event field, old streams become unreadable to new code, and every projection since the beginning is affected. Correct with additive-only evolution plus upcasters, and a lint rule that event type definitions are append-only in the schema module. A fourth is lag blindness: consumers silently see stale data and support tickets diagnose it before monitoring does. Correct with per-projection lag metrics surfaced to product owners, not only to engineers. A fifth is the write-your-own-query escape hatch: engineers query the event store directly under deadline pressure, coupling response latency to replay cost. Correct by making a cheap catch-all projection the sanctioned alternative and reviewing store-access policy quarterly.

## Limitations

Segregation buys read and write independence at the price of eventual consistency on every read path, and product surfaces must be designed for it — confirmation screens, pending states, and read-your-writes pins are UI costs that never appear in the architecture diagram. The pattern multiplies artifacts: each query shape is a projection with its own fold, consumer, checkpoint, and rebuild procedure, so a system with many read shapes carries many small components to operate. Rebuilds of large projections are expensive and compete with live consumption for resources, forcing rebuild windows or shadow infrastructure. The event store's append-only growth demands compaction or snapshotting policy, which is additional machinery with its own failure modes. Debugging spans two sides joined only by asynchronous consumption, so reproducing a state requires replay tooling and disciplined event capture. Finally, CQRS with an event store is a poor fit for domains with modest read load and simple invariants, where a single well-indexed model delivers the same behavior with a fraction of the moving parts; the pattern earns its complexity only under genuinely divergent read and write pressure.

## Canonical sources

- Fowler — CQRS (bliki): https://martinfowler.com/bliki/CQRS.html
- Microsoft Azure Architecture Center — CQRS pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs
- Fowler — Event Sourcing (the write-side system of record this article builds on): https://martinfowler.com/eaaDev/EventSourcing.html
- Microsoft Azure Architecture Center — Event Sourcing pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
