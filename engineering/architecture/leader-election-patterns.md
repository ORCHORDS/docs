# leader-election-patterns

**Issue:** A horizontally scaled worker fleet runs scheduled jobs, stream-batch coordination, or cache warmup, and every instance cheerfully does the work — emails send three times, the nightly aggregate double-counts, cleanup jobs race each other into corruption. Azure's Architecture Center describes the problem precisely: the instances are peers with "no natural leader that can act as the coordinator or aggregator," so the system needs a robust mechanism to elect exactly one coordinator and re-elect when it dies. Done casually (a database row flag, a cron job on "the" server), leadership becomes a split-brain generator: two nodes each believe they are the leader and nothing in the system can overrule them. Leader election is a solved problem with known algorithms and off-the-shelf primitives, but only if you adopt them deliberately, including the failure-detection and fencing details that make the election actually safe.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Principles

1. **Elect one, but everyone must be electable.** All task instances run the same code and any of them can lead, so the election process must be managed carefully "to prevent two or more instances taking over the leader position at the same time." The mechanism, not the deployment order, decides leadership.
2. **Leadership is a lease, not a title.** The leader holds a time-bounded grant it must keep renewing; if it stalls or partitions, the lease expires and another instance takes over. Azure's blob-lease sample works exactly this way — the leader periodically renews, and if renewal fails, the leader task is cancelled.
3. **Failure detection is a tunable, not a constant.** How quickly you must detect leader failure is system-dependent: some systems function briefly leaderless while transient faults heal; others must trigger re-election immediately. Define the detection window per workload, because it trades availability against false failovers.
4. **The coordinator is not the bottleneck.** The leader's purpose is to coordinate subordinates, and it doesn't necessarily participate in the work itself — though it should be able to if not elected. Leaders that also do all the work recreate the single point of failure the pattern exists to remove.
5. **Election is nondeterministic.** Azure notes you cannot assume which instance will acquire the lease. Never encode expectations about leader identity into application logic or ops runbooks.
6. **Fence the leader's side effects.** Election order and message delivery can interleave; downstream systems must be able to reject actions from a deposed leader (fencing tokens/epoch numbers checked on every effectful call), or you get split-brain behavior despite a correct election.

## Implementation Approaches

1. **Lease/mutex racing on a managed service.** Instances race to acquire a shared lease — a blob lease in Azure's sample, a lock key in Redis with TTL, or a CompareAndCreate in a CP store; the winner leads, renews periodically, and others poll to take over on expiry. This is the pragmatic default because the coordination service owns the hard parts.
2. **Consensus algorithms (Raft, Bully, Chang and Roberts).** Azure lists these as the alternative when you can't depend on an external coordinator: candidates have unique IDs and reliable communication, and the algorithm itself guarantees a single leader. Use an embedded library (etcd/raft, Apache ZooKeeper recipes) rather than implementing from the paper.
3. **Coordination service as third party.** ZooKeeper or etcd ephemeral nodes plus watches: each candidate registers an ephemeral znode; whoever owns the lowest sequence number leads; everyone watches the node ahead of them. This bundles election, failure detection (session expiry), and notification in one primitive.
4. **Heartbeat monitoring with takeover.** Subordinates monitor the leader through heartbeats or polling; when heartbeats stop, survivors run the election. Tune heartbeat interval against the lease TTL so detection precedes expiry rather than racing it.
5. **Graceful shutdown hooks.** On scale-in (the autoscaler "could terminate the leader if the system scales back"), the leader must release the lease and hand off in-flight coordination state; otherwise every scale-in event is an unplanned outage of exactly the wrong instance.
6. **Shadow leadership for fast failover.** Have the runner-up pre-load coordination state so promotion is instant; this matters when the leader holds expensive warm state (shard assignments, cache maps).

## Gotchas and Failure Modes

1. **Split brain via GC pause or network partition.** A paused leader wakes up still believing it leads while a new leader has been elected; without fencing tokens on side effects (emails sent, rows written), both act as leader. Every effectful leader action must carry and have checked a monotonically increasing epoch.
2. **The coordinator is a single point of failure.** Azure's sample is blunt: the blob (or Redis, or ZooKeeper ensemble) becomes the SPOF of the election. Choose a coordination service with availability targets better than the thing being coordinated, and have a documented degraded mode when it is unreachable.
3. **Stalled leader keeps renewing.** If the leader's task hangs but its renewal loop keeps running, no one else can take over — Azure calls this out explicitly: "the health of the leader should be checked at frequent intervals." Renewal must be coupled to actual health of the coordinated work, not just process liveness.
4. **Flapping elections.** Aggressive detection thresholds plus a jittery network produce leader churn, and each election drops in-flight coordination state. Add hysteresis (require N missed heartbeats, randomized election backoff) and alert on election frequency.
5. **Renewal/lease race conditions.** The delay between renewal requests must be less than the lease duration, or another instance legitimately acquires the lease between renewals; Azure's sample links the renewal task and the leader task so that failure of either cancels both.
6. **Locking would be simpler.** If all you need is coordinated access to a shared resource, optimistic or pessimistic locking is "a better solution" than electing a leader — reach for election only when there is genuinely coordinating work to own over time, not a single critical section.

## When (Not) To Apply

1. **Apply for singleton work in scaled-out fleets.** Scheduled jobs, stream-epoch coordination, cache warmup, and topology reconciliation across N identical replicas are the textbook cases.
2. **Apply when a third-party coordinator already exists.** If you run etcd/ZooKeeper/Consul for service discovery anyway, ephemeral-node elections are nearly free and battle-tested.
3. **Skip when there is a natural leader.** A dedicated singleton process or an existing primary (database primary, stream partition leader) already coordinates; adding an election layer duplicates it and adds failure modes.
4. **Skip when the platform provides the primitive.** Queue-based work distribution, database scheduler locks (e.g., `SELECT ... FOR UPDATE SKIP LOCKED`), and managed schedulers eliminate the need for application-level leadership in many workloads — prefer them before building election.
