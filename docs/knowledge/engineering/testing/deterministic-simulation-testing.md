# deterministic-simulation-testing

**Issue:** Distributed and concurrent systems fail in ways conventional tests cannot reach: rare message orderings, crash-at-the-worst-moment windows, partial network partitions, clock skew, and interleavings that occur once per millions of operations in production but never in a 5-minute integration test. Soak tests find a few of these slowly and non-reproducibly — you get a stack trace but not the schedule that caused it. Deterministic simulation testing (DST), pioneered by FoundationDB and now commercialized by Antithesis (founded by the FoundationDB team) and adopted by systems like TigerBeetle (whose VOPR harness runs continuously in CI), flips the model: the entire system, including simulated network, disks, clocks, and process failures, runs inside a single process driven by a seeded pseudorandom generator. Every scheduling decision is a function of the seed, so any failure found by hours or days of randomized simulation reproduces exactly, in minutes, from the seed alone. The engineering problem is structuring a system for determinism, building or adopting the simulation harness, and using fault injection that actually explores the interesting state space.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core mechanics

1. **Seeded schedule as the only source of randomness.** All nondeterminism — thread interleaving, message latency, faults, time itself — is drawn from one pseudorandom stream keyed by a seed. Two runs with the same seed execute identically, which is what turns a once-in-a-week failure into a one-command reproduction. FoundationDB's simulation and TigerBeetle's VOPR both work this way.
2. **Simulated environment, real code.** The production code runs unmodified in logic; only the platform layer (network sends, disk writes, timers, clock reads, entropy) is replaced by simulator implementations that route through the seeded scheduler. WarpStream's 2024-2025 case study describes simulating an entire SaaS this way — signup flows through Kafka workloads — finding correctness bugs random exploration surfaced in hours.
3. **Fault injection as a first-class driver.** The simulator injects crashes, partitions, disk corruption, reordered and duplicated messages, and clock jumps according to the seed. Antithesis's Determinator takes this further with a deterministic hypervisor that virtualizes hardware for unmodified binaries, so even the OS-level schedule is controlled.
4. **Invariants checked continuously.** Simulation runs assert global invariants after operations: replication counts, monotonically increasing versions, no lost acknowledged writes, cluster-state convergence. A DST run without invariant checks is just a slow fuzz test.

## Building for determinism

1. **Ban uncontrolled entropy and time.** Real system time, random number generators, and environment-dependent values (ports, PIDs, unordered map iteration) must flow through injected providers. Any hidden nondeterminism poisons reproducibility: the same seed produces different executions and the entire value proposition collapses.
2. **Single-threaded event loop or deterministic concurrency.** Either run components on a cooperative scheduler (the simulator decides when each task steps) or use frameworks that serialize concurrency deterministically (MADSim for C++, madsim for Rust, FoundationDB-style flow actors). Real OS threads with real locks are unsimulatable.
3. **Version-pin everything in the environment.** Compiler optimizations and allocator changes can alter timing in real executions but must not alter simulator behavior; keep the simulator's step ordering purely logical, not wall-clock driven, so a CI machine upgrade never changes results.
4. **Interface seam discipline.** Define a narrow platform trait (send, recv, persist, now, spawn, rand) with exactly two implementations: real and simulated. Systems designed with this seam (TigerBeetle, TigerBeetle-style storage engines) report that the seam itself improves production architecture, because side effects become explicit.

## Running DST in practice

1. **Continuous background exploration.** TigerBeetle runs VOPR continuously; teams with smaller budgets run simulation nightly and per-merge with a time budget, always persisting seeds of failing runs alongside CI artifacts so any failure is replayable indefinitely.
2. **Reproduction protocol.** On failure, capture seed, simulator version, and system commit hash. A bug is not "found" until a minimized reproduction exists: shrink by fixing more of the seed's choices and simplifying the workload until the smallest failing schedule remains. This mirrors classic delta-debugging.
3. **Assert on liveness too.** Beyond safety invariants (nothing lost, nothing corrupted), assert progress: the simulation must complete N operations within simulated time T. Liveness violations catch livelocks and starvation that crash injection provokes but unit tests never see.
4. **Coverage-guided schedule exploration.** Blind random schedules plateau; bias fault injection toward boundaries (exactly during commit, exactly between replica responses) and toward recently changed code, the same way good fuzzers bias toward diffs.

## Adoption realities and alternatives

1. **Cost-benefit threshold.** DST pays off for stateful, fault-tolerant infrastructure (databases, queues, consensus, replicated caches, payment ledgers). For stateless CRUD services, chaos experiments against a deployed environment (see chaos-testing-approaches) and property-based tests deliver most of the value at a fraction of the design constraint.
2. **Incremental strangling of nondeterminism.** Legacy services rarely qualify; the practical path is new components built on the deterministic seam first, with simulation added before the first production deployment, since retrofitting entropy and time through seams is a rewrite-scale change.
3. **Antithesis versus in-house.** Managed platforms remove the determinism requirements for many language runtimes via hypervisor-level control, letting ordinary nondeterministic programs be explored reproducibly; in-house harnesses cost months of platform work but keep the loop fully in CI with zero per-run spend. Decide by team size and how central correctness is to the product.
4. **Pair with model checking for protocol cores.** For the consensus or replication protocol itself, tools like Maelstrom (Jepsen's programmable testing platform) let you verify protocol logic against formal-ish models before layering full-system simulation on top.
5. **Do not skip the boring tests.** DST complements but does not replace unit, integration, and E2e layers; it excels precisely in the interleaving space those tests cannot enumerate.
