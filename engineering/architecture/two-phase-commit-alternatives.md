# two-phase-commit-alternatives

**Issue:** Two-phase commit (2PC/XA) is the textbook answer to "update several systems atomically": a coordinator asks every participant to prepare (vote), and if all vote yes, directs them to commit. The problem is what happens between the votes and the decision: participants that voted YES must hold locks and wait, and if the coordinator dies mid-protocol they can remain blocked indefinitely — the blocking-failure property documented since Gray's original analysis and reiterated in every modern deep dive (Wikipedia, TiKV's distributed-algorithm notes, singhajit.com's walkthrough). In a microservice world of REST APIs, NoSQL stores, and message brokers that do not speak XA, 2PC additionally requires every participant to support the same protocol and be simultaneously available, which caps availability at the product of all services' uptimes. Yet 2024-2025 practitioner threads (r/ExperiencedDevs) correctly push back on reflexive 2PC-hate: within one database or one tightly-controlled organization, 2PC is simple and gives real atomicity. The architectural skill is knowing exactly when 2PC is acceptable and which alternative — saga, outbox, TCC, consensus commit — fits each cross-service consistency need.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why 2PC Blocks and What It Costs

1. **The in-doubt window.** A participant that voted YES has durably promised to honor whatever decision arrives. If the coordinator crashes after collecting votes but before broadcasting the decision, the participant cannot unilaterally commit or abort (it does not know the other votes) — it holds locks until the coordinator recovers. Multiply by thousands of concurrent transactions and a coordinator outage becomes a fleet-wide lock jam.
2. **Lock amplification degrades throughput.** Every participating database holds row locks and maintains prepare state across multiple network round trips (prepare, then commit/abort), so throughput is bounded by the slowest participant and the longest round trip. Under load, the coordination overhead compounds: coordinators become the bottleneck and their recovery logs become an operational liability.
3. **The double-failure unrecoverable case.** If the coordinator and one cohort member fail during the commit phase, the remaining participants can be stuck permanently in a state that cannot be resolved by protocol — the classic result that made 2PC "not dependably recoverable." Paxos Commit (Gray & Lamport) exists precisely to fix this by replacing the single coordinator's decision with a consensus decision, at the cost of running consensus per transaction.
4. **Heterogeneity mismatch.** XA drivers are uneven across modern infrastructure: HTTP APIs, Cassandra/DynamoDB-style stores, and most message brokers do not participate. A "distributed transaction" that only spans two MySQL instances is a narrow use case in a microservice topology.

## When 2PC Is Actually Fine

1. **Single database, multiple storage engines.** InnoDB-style internal 2PC (redo log + binlog) is invisible to the application and correct — this is not the risky kind. Similarly, one PostgreSQL primary with partitioned tables does internal two-phase coordination safely.
2. **Homogeneous, co-administered systems.** Two or three databases run by the same team, same datacenter, with a battle-tested transaction manager and rehearsed recovery runbooks (what to do with in-doubt transactions after a coordinator crash). Practitioner consensus: this is where 2PC still earns its keep versus the operational weight of sagas.
3. **Short-lived, lock-light transactions.** If the protected resources are cheap to hold (no user-visible rows), the blocked-window risk is mostly a throughput concern, not a correctness cliff. Long-running business workflows never qualify — holding locks across human-time steps is the classic anti-pattern that motivated sagas in the first place.

## Alternative: Saga with Compensation

1. **Decompose into local transactions plus compensations.** Each step commits locally; on later failure, previously-completed steps are undone by compensating transactions (refund the charge, release the reservation). No locks are held across steps, so availability and latency scale per-service. The trade: isolation is abandoned — intermediate states are visible, so designers must handle "order exists but payment pending" as a first-class state.
2. **Orchestration vs choreography.** An orchestrator (a saga/process-manager instance) explicitly drives steps and compensations — easier to reason about, one place for timeout and retry policy. Choreography via events avoids the central component but scatters the workflow across consumers, which gets unreadable beyond ~4 steps. The repo's process-manager-vs-saga and saga-pattern-orchestration articles carry the full comparison.
3. **Compensations are semantically weaker than rollback.** A compensation cannot un-send an email; it must be a business-level undo (cancellation notice), and it must be idempotent and retryable because it will occasionally run twice. Design compensations alongside forward operations, never after.
4. **Counter-measures for lost isolation.** Use semantic locks (status = PENDING rows), commutative updates where possible, and pivot-transaction design (one non-compensable step placed last, after which the saga is guaranteed to complete). These are the standard countermeasures from Garcia-Molina's original saga work and remain current guidance.

## Alternative: Outbox, TCC, and Consensus

1. **Transactional outbox for state-plus-event atomicity.** The most common "distributed transaction" need is really "update my DB and publish an event atomically." Write the event to an outbox table in the same local transaction, then a relay (Debezium/CDC or a polling publisher) publishes it. This removes the need for any cross-store protocol — see outbox-pattern for the internals.
2. **TCC (Try-Confirm-Cancel) for reservation semantics.** Each participant exposes Try (reserve resources), Confirm (commit the reservation) and Cancel (release). Unlike 2PC, TCC reservations are business-level — a reserved inventory slot, a held balance — so no database locks cross the protocol, and confirm/cancel are idempotent retries. Cost: every service must implement three operations correctly; popular in payments-heavy Chinese e-commerce stacks and gaining attention in Western write-ups as a 2PC successor.
3. **Consensus-backed commit for genuine atomicity needs.** Systems like TiKV/Percolator-style designs (and RonDB's non-blocking 2PC) run the commit decision through Raft/Paxos-replicated state or use consensus to place the primary lock, eliminating the single-coordinator failure mode. This is the engineering answer when you truly need 2PC semantics without 2PC's blocking — it is what NewSQL databases do internally, and application teams should usually adopt such a database rather than reimplement it.
4. **Reconciliation as the safety net.** Whatever alternative is chosen, run periodic reconciliation jobs comparing the systems that "should" agree. Sagas fail mid-flight; outbox relays stall; reconciliation is the backstop that converts silent divergence into an alert queue item. Budget for it from day one.

## Decision Rules

1. **One database: plain local transactions.** Do not introduce any distributed machinery — the first instinct on "make these two services consistent" should be questioning the service boundary.
2. **Same-team, same-DC, homogeneous stores, short transactions: 2PC/XA is defensible.** Write the in-doubt-transaction runbook before going live.
3. **Long-running, multi-team, cross-network workflows: saga + outbox + idempotency.** Accept eventual consistency, engineer compensations and countermeasures, expose intermediate states in the UX.
4. **Hard atomicity across stores, high value per transaction: a consensus-native database.** Let the database's internal Percolator/Raft machinery do it; do not hand-roll.
5. **Related articles.** two-generals-problem for why atomic commit across an asynchronous network is fundamentally hard; exactly-once-delivery and idempotency-design for the delivery-side guarantees every alternative relies on.
