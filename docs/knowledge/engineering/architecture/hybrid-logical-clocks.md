# hybrid-logical-clocks

**Issue:** Distributed systems need timestamps that are simultaneously causally correct (if event A happened before B, A's timestamp is less than B's) and close to physical time (so humans and applications can query "state as of 14:00"). Physical wall clocks alone cannot provide this: NTP-synchronized clocks on different nodes disagree by milliseconds, can jump backwards, and two events on different nodes can get out-of-order physical timestamps even when one caused the other. Pure logical clocks (Lamport, vector) give causal ordering but carry no wall-clock meaning, and vector clocks grow with node count. Hybrid logical clocks (HLC), introduced by Kulkarni et al. in 2014 and now the timestamping backbone of databases like CockroachDB and YugabyteDB, combine a physical component with a logical counter to get both properties — but the architecture must respect their limits: bounded clock skew, uncertainty windows, and node suicide when drift exceeds the bound.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How HLC Works

1. **Structure: (physical, logical).** An HLC timestamp pairs the largest wall-clock time the node has observed (physical component) with a logical counter. On a local event, if wall time advanced past the physical component, adopt it and reset the counter to zero; otherwise increment the counter. On receiving a message, take the maximum of local wall time, local physical component, and the message's physical component, incrementing the counter on ties. The result is monotonic per node and causally ordered across nodes.
2. **Causality guarantee.** If A happened-before B (same node sequence, or A's send preceded B's receive), then HLC(A) < HLC(B) — Lamport-clock causality is preserved because every causal edge ratchets the physical or logical component upward. Concurrency (no causal path) gets no ordering promise, which is correct: the events genuinely have no order.
3. **Closeness to physical time.** The physical component is bounded within the assumed clock-skew bound of real time, so HLC timestamps remain interpretable as wall-clock instants — unlike pure logical clocks, an HLC value can be used for TTLs, retention windows, and "as of" queries. The logical counter only inflates past wall time when a node is talking to nodes with ahead-running clocks or emitting faster than clock resolution.
4. **Comparison to Lamport clocks.** Lamport gives causal order but values are step counts unrelated to time. HLC is essentially a Lamport clock anchored to wall time, inheriting causality while regaining interpretability — at the cost of dependence on the skew bound being honest.
5. **Comparison to vector clocks.** Vector clocks detect concurrency (you can tell that two events are unordered, enabling merge semantics in CRDTs); HLC cannot — it totally orders even concurrent events. Choose vector clocks when you need to distinguish concurrent from causal; choose HLC when you need a sortable, wall-meaningful timestamp.

## Architectural Uses

1. **MVCC transaction timestamps.** CockroachDB assigns each transaction an HLC timestamp; every version of a row carries one, and reads see the newest version at or below the read timestamp. This is what makes snapshot reads and time-travel queries (AS OF SYSTEM TIME) possible on a distributed cluster.
2. **Event ordering and dedup.** Using HLCs as event timestamps in an event-sourced or replicated log yields a total order that respects causality, and near-wall-clock values make replay windows and retention filters expressible in human time. The logical component breaks sub-millisecond ties that wall clocks cannot.
3. **Cross-service request tracing and audit.** An HLC propagated through message headers lets downstream services order events across service boundaries consistently with causation, which naive now() timestamps violate whenever clocks skew.
4. **Conflict resolution input.** Last-writer-wins registers keyed on HLC instead of wall clock remove the classic anomaly of a slow-clock node overwriting newer data; combined with the uncertainty bound, it is the standard underpinning of geo-distributed LWW (as in Dynamo-style stores and Cosmos DB-style conflict handling, which use closely related hybrid logical/synthetic clocks).

## Bounds, Drift, and Operational Rules

1. **The max-offset contract.** HLC correctness depends on clock skew staying within a configured bound — CockroachDB's default max offset is 500ms, and Cockroach Labs' current production guidance recommends lowering it to 250ms for new multi-region clusters to cut write latency on global tables. Every consumer of HLC timestamps must define this bound and instrument for it; an unbounded assumption silently becomes a correctness bug.
2. **Node self-shutdown on drift.** CockroachDB nodes monitor relative offset against peers and self-terminate when drift reaches roughly 80 percent of max offset — a live node with an untrustworthy clock is worse than a dead node, because it can mint timestamps outside the uncertainty envelope and corrupt linearizability. Any HLC-based design needs an equivalent containment story.
3. **Time-source uniformity.** All nodes must sync to compatible time sources: current docs warn that Google and Amazon time sources (leap-second smeared) are incompatible with the default NTP pool (unsmeared) — mixing them manufactures systematic skew at leap seconds. Prefer Amazon Time Sync or Google Public NTP, or chrony with client-side smearing, consistently fleet-wide.
4. **Forward-jump and VM-suspension defenses.** Clocks jumping forward (vMotion pause/resume, hypervisor time bugs) produce physically-impossible timestamps; enable forward-jump detection (CockroachDB's server.clock.forward_jump_check_enabled) or use a PTP hardware clock device where jumps are expected and legitimate.
5. **Uncertainty-interval restarts.** A reader at timestamp t cannot trust data written with timestamps inside its uncertainty window (t, t + max_offset), because the writer's clock may genuinely be ahead. Databases handle this by restarting or extending the transaction — application architects must expect and budget for these restarts instead of treating them as errors.
6. **Never expose raw HLC as user-facing time.** HLC physical components can read slightly in the future relative to any single node's clock; render display times from a separate wall-clock field, and keep HLC strictly for ordering.

## Related Patterns

1. **Two-generals and CAP context.** HLC sidesteps neither coordination cost nor partition tradeoffs; it orders events given communication, and remains subject to the same fundamental limits (see two-generals-problem, cap-theorem-explained).
2. **Leader election and leases.** Lease expiry decisions combine timeouts with ordering; HLC-based timestamps make lease-issued versions consistent with causality across failovers.
3. **Event sourcing.** HLCs are a strong candidate for event stream versioning where multi-writer ordering matters — complements event-schema-versioning, which handles the payload side.
