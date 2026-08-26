# priority-queue-architecture

**Issue:** Most distributed queues treat every message as equally urgent, and that assumption collapses the moment one class of work must jump the line — a payment fraud check, a production incident alert, an interactive user request competing against background batch jobs. Adding priority to a distributed queue is deceptively hard: naive strict priority starves low tiers to death, priority inversion appears when shared resources interact with priority levels, and head-of-line blocking lets one giant low-priority job clog a worker that a tiny high-priority job needs. Modern practice, reflected in Klaviyo's Kafka priority queue writeup, Temporal task queues, and a 2025 academic survey of priority queuing under heavy workloads, treats priority as a scheduling architecture decision with explicit starvation budgets, weighted fairness, and per-tier observability — not a numeric field you add to a message schema and hope.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Topologies

1. **Multi-tier topics or queues.** The dominant broker-side design: one topic/queue per priority tier (critical, high, default, bulk). Consumers drain tiers in weighted order — for example, always empty critical before default, or poll critical twice as often. Klaviyo's implementation on Kafka follows this shape, with fairness tuning so background tiers still make progress.
2. **Broker-native priority support.** RabbitMQ supports per-message priority via the priority property on priority-declared queues; ActiveMQ and SQS (FIFO with message groups, or separate queues) offer adjacent mechanisms. Broker-native priority is convenient but usually has hard limits (RabbitMQ caps effective priorities at 10) and does not itself prevent starvation.
3. **Centralized sorted structure.** Redis sorted sets with (score, job-id) members, or a database table with an ordered index, give a custom scheduler full control of the ordering function at the cost of operating a centralized component that must be sharded or replicated as throughput grows.
4. **Scheduler-managed queues.** Kubernetes-style scheduler plugins, Nomad fair-share, or YARN hierarchical capacity queues implement priority plus preemption and capacity guarantees. This is the right model when the "queue" is really a resource scheduler allocating CPU and memory, not just passing messages.

## Starvation Mitigation

1. **Aging.** The classic remedy per the priority-starvation literature: a job's effective priority increases with wait time so that any waiting job eventually beats fresh high-priority arrivals. A distributed implementation stores enqueue time and computes effective priority at pop time, or runs a periodic promotion job that moves aged messages up a tier.
2. **Weighted fair queuing.** Instead of strict tier order, guarantee each tier a minimum share of consumption capacity (say, 70/20/10) so lower tiers always make progress. Weighted polling between tier topics is the simplest distributed approximation and prevents bulk work from dying during a sustained high-priority incident.
3. **Capacity floors and admission control.** Reserve a fraction of workers exclusively for lower tiers, or reject/throttle high-priority submissions when they would consume more than their declared budget. Admission control at the front door is cheaper than starvation discovered hours later.
4. **Bounded batch mixing.** Per the starvation-free priority queue implementations in the wild, mixing a small ratio of lower-tier jobs into every consumption batch bounds the maximum wait for low-priority work while keeping high-tier latency low.
5. **Explicit SLOs per tier.** Define a target max wait per tier (critical under 1s, bulk under 1h) and alert on the oldest-message age per tier. Starvation then shows up as an alert, not as a customer complaint.

## Priority Inversion Hazards

1. **Shared-resource inversion.** A high-priority job blocked on a lock or row held by a low-priority job inverts the whole system. In distributed settings this appears as head-of-line blocking on a shared consumer. Mitigate with short critical sections, per-tier connection pools, or priority inheritance where the platform supports it.
2. **Head-of-line blocking in batch consumers.** If a worker prefetches 50 default-tier jobs, a critical job behind them waits for the whole batch. Cap prefetch sizes, or use per-tier consumer groups so critical jobs never share a worker's in-flight window with bulk work.
3. **Cross-tier deadlocks via ordering.** Two jobs at different priorities locking the same two rows in opposite order deadlock; the deadlock detector kills one, usually the wrong tier. Standard remedy: deterministic lock ordering, or route same-entity work to the same tier.
4. **Downstream priority blindness.** Your queue tiering ends at the queue; downstream services (a database, an external API) see plain traffic. A burst of critical-tier work can still queue behind bulk calls in a shared downstream pool — propagate tier into downstream timeouts, circuit breakers, and bulkhead allocations.

## Operational Concerns

1. **Per-tier observability.** Track queue depth, oldest message age, throughput, and failure rate per tier, not aggregate. A healthy average with a growing critical-tier depth is an outage in progress.
2. **Per-tier dead-letter queues and alerting.** Critical-tier failures must page; bulk-tier failures can batch. Separate DLQs per tier let you route them differently and prevent a poisoned bulk message from drowning critical-failure signals.
3. **Backpressure by tier.** When the system is overloaded, decide explicitly which tiers shed load, which slow producers, and which queue unbounded. Load shedding policy per tier should be written down before the incident, not improvised during it.
4. **Poison message isolation.** A failing high-priority message retried forever starves its tier from behind. Bound retries per message, then park it in a per-tier DLQ with the priority context preserved for manual replay.
5. **Testing under inversion conditions.** Load tests should include sustained high-tier traffic mixed with bulk backfill, specifically to verify the fairness policy and aging parameters hold. Fairness bugs only appear under contention, never in idle systems.

## Decision Guide

1. **Start with multi-tier queues and weighted polling.** It works on every major broker, keeps tier logic in one place, and is easy to reason about. Reach for sorted-set schedulers or scheduler plugins only when weighted polling measurably fails the tier SLOs.
2. **Keep priority classes few and stable.** Three to five tiers with documented membership rules. Every additional tier multiplies fairness tuning and monitoring surface.
3. **Make priority a producer-side contract, not a consumer guess.** Producers assign tier by policy (interactive vs batch, paid vs free, incident vs routine); consumers enforce fairness. If consumers could guess priority, you would not need the queue to carry it.
4. **Revisit parameters with load data.** Aging rates and weight ratios are empirical constants. Instrument them, review quarterly, and expect to change them as traffic mix shifts.
