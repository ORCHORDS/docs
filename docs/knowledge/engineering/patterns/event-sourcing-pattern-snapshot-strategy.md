# Event Sourcing Pattern Snapshot Strategy

## Scope

This article covers snapshotting within event-sourced systems: persisting periodic materialized summaries of an aggregate's state so that rebuilding does not require replaying every event from origin. Scope covers when to snapshot, snapshot placement and cadence, the transactional relationship between events and snapshots, restoring from snapshots plus subsequent events, snapshot schema evolution, and verification that snapshot-derived state equals replay-derived state. It assumes an event store as system of record; it does not cover event store selection, projection design, or CQRS segregation generally.

## Workflow or implementation guidance

Snapshot when replay cost becomes a product problem, not before. The trigger is measured: median and p99 aggregate event counts, replay time for the largest aggregates, and the latency budget of the request paths that rebuild state. A common placement policy is every N events (for example every hundred) or every M days per aggregate, whichever comes first, chosen so that the worst-case restore replays at most N events. Snapshots written too eagerly waste storage and write throughput; snapshots written too rarely leave the tail-latency problem the strategy was meant to solve.

Write snapshots asynchronously, derived from the event stream, never as a parallel source of truth:

```ts
async function maybeSnapshot(id: AggId, version: number, store: EventStore): Promise<void> {
  if (version % SNAPSHOT_INTERVAL !== 0) return;
  const state = await replayEvents(id, afterLastSnapshot(id)); // fold from previous snapshot
  await store.writeSnapshot(id, version, serialize(state));    // tagged with stream version
}
```

Restoration always folds forward from the newest snapshot whose version is less than or equal to the stream's current version, applying events after that version. The critical correctness rule is that a snapshot must carry the exact stream version it summarizes; a snapshot without its version anchor cannot be combined safely with subsequent events and invites double-application or skipped events.

Because snapshots are derived data, their writes need not be transactional with event appends — a lost or stale snapshot costs only replay time, never correctness. That property is the strategy's greatest strength: snapshots can be regenerated, backfilled for old aggregates, migrated to a new schema wholesale, and deleted without ceremony. Exploit it: treat snapshots as a cache with a lifecycle, not as data you must preserve.

Serialization discipline follows from that framing. Serialize explicit, versioned state — a schema with a version field and nullable new fields — rather than language-native object dumps. Native serialization bakes in implementation details, so a refactor that renames a private field silently makes every existing snapshot unreadable, and the failure appears as a runtime error on restore months after the refactor shipped.

## Controls

Gate snapshotting on measurement: no snapshot policy is enabled until replay-time telemetry justifies it, and the interval is revisited against current event-count distributions on a schedule, because traffic growth quietly turns a fine interval into an inadequate one. Enforce version anchoring with a write-path assertion — a snapshot row without a stream version fails validation — and a restore-path assertion that applied events begin strictly after the snapshot version. Control schema evolution additively: new fields optional and defaulted, renames expressed as new fields with migration on read, and every snapshot schema version registered with a documented compat policy. Alert on restore-path anomalies: restores that fall back to full replay more often than a threshold indicate snapshot staleness or write-path failures. For storage governance, track snapshot bytes as a fraction of total event-store bytes per aggregate type; unbounded growth signals an interval tuned for read latency without regard to write economics.

## Validation evidence

The single most important verification is equivalence: for a sampled set of live aggregates, rebuild state twice — once from snapshots plus subsequent events, once by full replay from origin — and assert deep equality. Run this continuously in staging on every deploy (it catches serialization bugs, schema drift, and fold non-determinism) and periodically in production against real streams. Truncation tests validate the restore path precisely: given a stream of length well past two snapshot intervals, restore with each available snapshot and assert identical state, proving that any valid starting snapshot yields the same result. Schema-migration test: restore an aggregate whose snapshots span two schema versions and assert a uniform final state, exercising the migration-on-read path. Concurrency test: two actors snapshotting the same aggregate at different versions interleaved with appends, then restore, and assert correctness regardless of which snapshot wins — snapshots at slightly stale versions must be safe. Production evidence: replay-time distribution per aggregate type before and after enabling snapshots, demonstrating the p99 improvement that justified the strategy, plus the measured write-cost delta from snapshot generation.

## Failure modes and correction

The signature failure is snapshot corruption silently accepted: state restored from a snapshot diverges from true replay, and every decision made by that aggregate instance thereafter is wrong with no error raised. Correct with the continuous equivalence check and by checksumming snapshot payloads against a fold of the summarized events at write time. The second failure is version-anchor loss: snapshots stored without their stream version, restore logic guesses the offset, and events are skipped or double-applied. Correct by making the version column mandatory and asserting monotonicity on write. The third is native-format coupling: language-native serialization, a refactor, and then restores failing or silently defaulting fields on old snapshots. Correct with explicit versioned schemas and a restore path that treats unknown snapshot schema versions as a miss (fall back to replay) rather than an error. A fourth is snapshot write contention: synchronous snapshotting inside the command path adds latency spikes every Nth command. Correct by moving snapshot generation off the command path — a background task or consumer that snapshots at the interval. A fifth is interval calcification: the aggregate's event volume grows tenfold over two years, worst-case restore exceeds its latency budget, and nobody connects the symptom to the interval. Correct by monitoring restore-time distribution per aggregate type and alerting on budget breach.

## Limitations

Snapshots optimize single-aggregate reconstruction only; projections, analytics, and cross-aggregate queries rebuild from the full event stream regardless and need their own strategies. The strategy adds a second serialized representation of every state that must be kept compatible with the event schema across versions — permanent additional evolution burden on exactly the schema that is hardest to change. Storage cost roughly doubles for snapshotted aggregate types at aggressive intervals, and the write-amplification lands on the event store, which is usually the least scalable component in the design. Snapshot cadence is a per-aggregate-type tuning decision with no globally correct value, so operating many aggregate types means operating many policies. Debugging becomes two-layered: a state anomaly might originate in an event, in the fold, or in a stale snapshot, and distinguishing them requires tooling most teams build only after the first bad incident. Finally, for aggregates with naturally bounded event counts, snapshots are pure overhead with no benefit — the pattern should be applied per aggregate type based on measured distributions, not uniformly across the domain.

## Canonical sources

- Fowler — Event Sourcing: https://martinfowler.com/eaaDev/EventSourcing.html
- Microsoft Azure Architecture Center — Event Sourcing pattern (snapshots as a mitigation for performance and scalability): https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
- Chris Richardson — microservices.io, Event Sourcing pattern: https://microservices.io/patterns/data/event-sourcing.html
