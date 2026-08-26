# materialized-view-maintenance

**Issue:** A CQRS read model, denormalized projection, or precomputed summary view made queries fast — and then rotted. The view drifts from the source data, refreshes hammer the primary at the top of every hour, a backfill takes the dashboard down, and nobody remembers whether the view can be safely rebuilt from scratch. Microsoft's Azure Architecture Center frames the pattern's key property: a materialized view "is completely disposable because it can be entirely rebuilt from the source data stores" and "is never updated directly by an application — it's a specialized cache." Teams treat the view as precious state instead of a cache with a maintenance lifecycle, and that single misconception causes most production incidents in event-sourced and CQRS systems. The maintenance strategy — how and when the view updates, rebuilds, and reconciles — must be designed, monitored, and tested like any other subsystem.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Principles

1. **The view is disposable by definition.** Because it can always be regenerated from source data (or the event store), the architecture must keep the rebuild path real: versioned projection code plus a repeatable rebuild pipeline. If you cannot rebuild it, it is not a materialized view — it is the system of record, and it is in the wrong place.
2. **Update policy is a first-class design decision.** Azure guidance: ideally the view regenerates in response to a change event, but that causes excessive overhead when source data changes rapidly; alternatives are a scheduled task, an external trigger, or manual regeneration. Pick the trigger deliberately per view, based on change rate and staleness tolerance.
3. **Staleness is a budget, not an accident.** Define the maximum acceptable lag per view (e.g., "orders summary ≤ 5 min, user profile ≤ 1 s"), instrument actual lag, and alert on breach. Without a stated budget, drift is invisible until a user notices.
4. **Views are query-specific.** Materialized views "tend to be specifically tailored to one, or a small number of queries," and multiplying views multiplies storage cost and update fan-out. Consolidate ruthlessly; every view must name the query it exists to serve.
5. **Consistency of the view is bounded by its update mechanism.** If the source changes while the view is generating, the view will not be fully consistent with the original — schedule generation accordingly, and design consumers to tolerate or detect the window.
6. **Location is free — exploit it.** The view need not live in the source store or partition; it can join data from several partitions or stores (e.g., a write-optimized cloud store as source, a relational read store for views). Maintenance tooling must therefore be cross-store aware.

## Implementation Approaches

1. **Event-driven incremental updates.** Subscribe to the outbox/change-data-capture stream and apply per-entity deltas (upsert one row per event). This is the default for event-sourced systems, where prepopulated views examining events "might be the only way to obtain information from the event store." Track per-partition offsets in a checkpoint table so updates resume where they stopped.
2. **Idempotent, versioned projection handlers.** Handle events with a consumer-group offset keyed to (view version, partition); bump the view version whenever projection logic changes. Storing the schema/handler version per row lets you detect rows written by old logic during migration windows.
3. **Dual-write cutover for logic changes.** Run the new projection version in parallel writing to a shadow view, compare outputs on sampled entities, then switch reads atomically and retire the old view. Never mutate projection logic in place against the live view.
4. **Snapshot + catch-up rebuilds.** For full rebuilds, take a consistent snapshot of source state (or event-store checkpoint), build the new view offline, then replay events from the checkpoint to the present before swapping. This keeps the serving view untouched during rebuild and bounds the swap-gap to replay time.
5. **Scheduled batch refresh for slowly-changing aggregates.** For weekly-report-style summaries, Azure's own example, a scheduled task is more appropriate than event overhead — rapid-change sources make per-event regeneration prohibitively expensive.
6. **Tiered storage per reliability needs.** Because a transient view used only to improve query performance can live "in a cache or in a less reliable location," put hot small views in Redis and large analytical views in a column store; only durable correctness requires durable storage. Index the view where the storage engine supports it.

## Gotchas and Failure Modes

1. **Poison events stall the whole view.** One malformed event blocks the consumer and freezes staleness for everyone. Dead-letter failures per event, keep the offset moving, and reconcile the skipped entities in a repair job.
2. **Out-of-order and late events corrupt aggregates.** Make handlers commutative where possible (additive counters, set semantics), or key rows by event time so late arrivals recompute their bucket instead of double-counting.
3. **Silent divergence.** Incremental updates miss deletes, partial failures, and buggy handlers, and nothing notices. Run a periodic reconciliation (counts/checksums of source vs view, or sampled entity comparison) and page on deltas beyond threshold.
4. **Rebuild storms.** Multiple views rebuilt simultaneously saturate the source store or event store. Queue rebuilds, rate-limit event-store reads, and schedule backfills off-peak.
5. **Storage-cost creep.** Each new query begets a new view; fan-out on every write grows unbounded. Audit views quarterly against their named queries and delete orphans — an unmaintained view is worse than no view because it is trusted and wrong.
6. **TTL'd caches confuse maintenance logic.** If the view lives in a cache that expires independently (e.g., DAX in front of a global table bypasses cache on writes), stale entries outlive the update pipeline's assumptions; align cache TTLs with the staleness budget.

## When (Not) To Apply

1. **Apply in event-sourced and CQRS systems.** Where the store holds only events, materialized views are the only way to obtain current state — maintenance tooling is part of the core product, not an optimization.
2. **Apply for expensive cross-store joins.** Bridging a write-optimized store and a query-optimized one via maintained views is one of the pattern's strongest uses.
3. **Skip when source data is simple and easy to query.** Direct queries with proper indexes beat a maintained copy; the view's maintenance cost buys nothing.
4. **Skip when consistency is a high priority and staleness is unacceptable.** Azure's guidance is explicit: where views must always match the source, the pattern's eventual consistency is the wrong trade — query the source, or accept stronger consistency primitives in the store itself.
