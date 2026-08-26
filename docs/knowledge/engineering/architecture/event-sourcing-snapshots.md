# event-sourcing-snapshots

**Issue:** Event-sourced aggregates rebuild state by replaying every event in their stream, so load cost grows linearly with stream length. An aggregate with 100,000 events takes seconds to rehydrate on every command, turning a write path into a full-history scan. Snapshots — periodic persisted captures of aggregate state at a given version — are the standard fix, but they are frequently applied too eagerly: the 2026 "snapshot paradox" argument from EventSourcingDB's maintainers is that replay cost is exaggerated for most domain models, and that snapshots add schema versioning burden, storage, and a second consistency surface exactly where the event store promised to keep things simple. The architectural problem is deciding when snapshots are justified, how to trigger and store them, and how to keep them from silently becoming a second source of truth.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When to Snapshot (and When Not To)

1. **Measure replay cost before adding snapshots.** Most aggregates never exceed a few hundred events and rehydrate in milliseconds; snapshot machinery added "just in case" is pure liability. Instrument rehydration time and stream length per aggregate type, and snapshot only the types whose p99 load cost is actually a problem.
2. **Fix the aggregate boundary first.** A stream that grows unboundedly is usually an aggregate-design smell — a Customer that absorbs every AddressChanged for a decade. Splitting the aggregate, archiving completed lifecycles into separate streams, or extracting sub-aggregates often eliminates the need for snapshots entirely, and 2025-era guidance consistently recommends this before reaching for snapshots.
3. **Count-based thresholds.** Snapshot once the number of events to load exceeds a threshold — Axon's canonical mechanism, with common configurations around 100-500 events (the widely-cited Baeldung example uses 250). Simple to reason about, and load cost becomes bounded at threshold-plus-interval.
4. **Time-based triggers.** Snapshot when the newest snapshot is older than a duration, which suits hot aggregates that are loaded constantly but updated irregularly — you pay for a refresh at most once per interval regardless of event count. Combining count and time triggers covers both high-frequency and slow-drip streams.
5. **Snapshot as a pure optimization.** A snapshot must be disposable: delete every snapshot and the system must still work (slower) by replaying from the beginning. If deleting snapshots breaks anything, snapshots have leaked into being source of truth, which is the core failure of the pattern.

## Storage Design

1. **Separate stream or store, never mixed into the event log.** EventStoreDB/Kurrent guidance is to write snapshots outside the domain event stream (a linked snapshot stream or a dedicated store/table), keyed by aggregate id and version, so tooling, projections, and audits over the event log remain unaffected.
2. **Record the version, atomically with the snapshot.** A snapshot is only valid for the stream version it captured; persist the last event number alongside the state and always replay events after that version. Loading must handle the race where new events landed between snapshot write and load.
3. **Version the snapshot schema.** Aggregate refactors change state shape; tag snapshots with a schema version and either migrate them on read (upcasting), store them in a self-describing format, or simply ignore incompatible snapshots and rebuild from events — the cheapest correct policy for most teams.
4. **Retention and churn.** Keep only the newest snapshot per aggregate (or the last two); every write does not need a snapshot, and old snapshots are dead weight that complicates storage growth accounting.
5. **Serialization honesty.** Snapshots capture internal state including framework internals (Axon's AggregateSnapshot serializes the aggregate object itself), which couples snapshot compatibility to code structure. Prefer explicit, minimal DTO-style snapshot payloads over serialized object graphs.

## Operational Pitfalls

1. **The snapshot paradox — premature optimization.** The EventSourcingDB maintainers' 2026 position: teams reach for snapshots on day one, then pay permanent versioning complexity to solve a performance problem they never had. Adopt snapshots reactively, driven by measured rehydration latency, not proactively as part of "proper event sourcing."
2. **Non-deterministic rehydration.** If event application depends on anything outside the stream (current time, exchange rates, random ids), a snapshot taken mid-history diverges from a full replay. Keep fold functions pure, or accept that snapshot path and replay path can disagree — and test both paths against the same event fixtures.
3. **Snapshot write contention.** Triggering a snapshot on every load-threshold crossing can have many concurrent commands racing to write snapshots; make snapshot writes idempotent and conditional (only if version is newer) so concurrent writers do not clobber each other.
4. **Testing the fast path.** Most event-sourcing tests exercise full replay because it is the default; add explicit tests that load via snapshot-plus-delta and assert identical resulting state, since this path only runs in production once snapshots exist.
5. **Rebuilds and projections are a different problem.** Snapshots accelerate command-side rehydration, not read-model rebuilds; query-side cost is addressed by projections and persistent subscriptions. Teams that conflate the two snapshot the wrong side of CQRS.

## Related Patterns

1. **Event sourcing and stream design.** Snapshot decisions follow from stream granularity — see event-sourcing-pattern and event-sourcing-strategy; the aggregate-root pattern bounds how long streams can grow.
2. **CQRS read models and materialized views.** The query-side complements to snapshotting, where the same "state derived from events, disposable by design" discipline applies.
3. **Event schema versioning.** Snapshot schema versioning inherits the same compatibility rules as event upcasting; a shared policy avoids two divergent versioning schemes.
