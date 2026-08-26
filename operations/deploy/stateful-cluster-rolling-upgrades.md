# stateful-cluster-rolling-upgrades

**Issue:** Rolling out a new version of a stateful cluster — a Kafka/ZooKeeper-or-KRaft broker fleet, an Elasticsearch/OpenSearch node set, a Redis with replicas, a Cassandra ring, or any StatefulSet where each pod has identity, a PVC, and a role in a quorum — does not behave like rolling a stateless Deployment. Pods must restart in a specific order, one at a time, with the cluster healthy between hops; a naive `kubectl rollout` or a node drain at the wrong moment can drop a partition leader mid-write, split a quorum, or trigger shard rebalancing that storms the disk for hours. This article covers the Kubernetes StatefulSet update mechanics (ordinal order, partition canaries, the v1.35 `maxUnavailable` knob, the forced-rollback trap), operator-specific patterns for Kafka (Strimzi) and Elasticsearch (ECK), and keeping PVC data safe while the fleet churns.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why stateful upgrades are a different exercise

1. **Pods have identity and rank.** A StatefulSet's pods carry stable ordinals (`web-0`..`web-N-1`) and hostnames; they are created lowest-to-highest ordinal but *updated and deleted highest-to-lowest*. Controllers, leaders, and data often live on specific ordinals, so update order is a correctness property, not an optimization.
2. **Readiness gates the next hop.** With the default `OrderedReady` + `RollingUpdate`, the control plane waits until an updated pod is `Running and Ready` (plus `minReadySeconds` if set) before touching its predecessor. One broker that never rejoins wedges the entire rollout — there is no automatic skip.
3. **Availability is per-partition/shard, not per-pod.** Strimzi's docs state the trade plainly: rolling updates maintain the *cluster's* availability but can still disrupt *clients* — a leader move is a latency blip or an in-flight-request failure even when the broker count never drops.
4. **Node drains are rolling updates you did not schedule.** A Kubernetes drain evicts pods regardless of your rollout plan; without a disruption budget enforcing one-at-a-time, a drain can take multiple brokers simultaneously. This is the single most common self-inflicted outage in broker fleets (see kubernetes-deploy-debugging.md for the debugging path).

## The Kubernetes update mechanics worth knowing cold

1. **`RollingUpdate` (default) walks ordinals N-1 down to 0, one pod at a time.** The doc behavior: delete-and-recreate each pod, wait for Ready, continue. For brokers this is the safe default pace; resist speeding it up until you know why you need to.
2. **`partition` stages a canary inside the same set.** With `rollingUpdate.partition: N`, only pods with ordinal >= N get the new template; pods below N stay old — and if deleted, are *recreated at the old version*. The docs recommend partitions for exactly this use: "stage an update, roll out a canary, or perform a phased roll out." Set partition to replicas-1 for a one-pod canary, verify, then lower it stepwise.
3. **`maxUnavailable` (beta in v1.35, off by default) lets multiple pods update at once.** It cannot be 0, defaults to 1, and enables bursting — faster, but pods may become ready out of order, which breaks strict-ordered fleets. Treat it as opt-in for fleets that have proven parallel-safe upgrades, not a default to flip globally.
4. **`OnDelete` gives you total manual control.** The controller updates nothing until you delete pods yourself — the right mode when upgrade steps live outside Kubernetes (run a migration tool, drain a broker's partitions, then delete the pod).
5. **The pod-index label enables ordinal-aware routing.** `apps.kubernetes.io/pod-index` and `statefulset.kubernetes.io/pod-name` labels let you route canary traffic to the highest ordinal or slice metrics by ordinal — the observability hook that makes staged rollouts debuggable.

## The forced-rollback trap (this bites everyone once)

1. **A bad template wedges the rollout at one ordinal.** With `OrderedReady`, if the new version's pod never becomes Ready, the rollout stalls mid-fleet: half the pods new and broken, half old. The set sits there indefinitely.
2. **Reverting the template is not enough.** Kubernetes' own docs warn that after reverting the spec you must also *delete the pods that were already attempted with the bad config* — otherwise the stuck pod keeps its bad spec, still never becomes Ready, and the rollout stays wedged even though the manifest looks correct now.
3. **Use ControllerRevisions, not `kubectl rollout restart`.** `kubectl rollout history statefulset/web` / `rollout undo --to-revision=N` operates on stored controller revisions; keep `revisionHistoryLimit` at its default of 10 and never set it to 0, or the undo target you need is gone (the container-image-tagging.md digest-pinning discipline applies to what those revisions reference).
4. **Rehearse the wedge path.** This trap is a drill scenario in rollback-drills-restore-testing.md terms: deliberately ship a failing readiness probe to staging, confirm the on-call knows the revert-and-delete-pods sequence, and time it.

## Broker fleets: Strimzi/Kafka patterns

1. **The PDB enforces one broker down at a time.** Strimzi creates a PodDisruptionBudget allowing a single unavailable pod, which both paces operator-driven rolling updates and stops node drains from evicting two brokers at once. The community discussions around `maxUnavailable: 0` PDBs and PDB-disabling options exist precisely because teams hit eviction deadlocks — read them before overriding.
2. **Let the operator drive broker restarts; let the Drain Cleaner translate evictions.** Strimzi's Drain Cleaner annotates pods evicted by node drains so the *operator* performs the restart with its broker-aware checks (topic/partition status) rather than kubelet doing a blind recreate. Running broker fleets on drain-capable nodes without this pairing is how drains become outages.
3. **Upgrade order: operator first, then Kafka.** The standard Strimzi sequence upgrades the operator, which then rolls brokers one at a time per its own readiness criteria — and the 2025 phased-upgrade guidance shows running *multiple operator versions across a fleet* during migration windows (staging fleet first, prod later) using kustomize overlays.
4. **Verify client impact, not just broker health.** Because cluster availability does not equal client smoothness, watch rebalance counts, produce/consume latency, and `UNDER_REPLICATED_PARTITIONS` between hops — the post-deploy-monitoring-checklist.md baselines, applied per ordinal.

## Search fleets: Elasticsearch/ECK patterns

1. **Do not manually exclude shard allocation during rolling upgrades.** The current guidance is that manual `cluster.routing.allocation.exclude` during *upgrades* is no longer recommended: since ES 6.8+, a restart auto-disables allocation and restores it after, and manually excluding can trigger exactly the shard-shuffling storm you were trying to avoid. Reserve allocation-exclude for *permanent* node removal (drain shards, then decommission), which is still the standard approach in OpenSearch operations.
2. **On ECK, prefer the shutdown API over exclude-based removal.** The ECK issues around transient `allocation.exclude` settings being left set (`_name: none_excluded` residue) are why the managed shutdown API replaced hand-rolled exclusion — it sequences drain-and-stop without leaving cluster settings behind.
3. **Mind the version-compatibility allocation decider.** During a mixed-version window, Elasticsearch's allocation deciders restrict which shards can live on which version — going too fast (or restarting a data node before its shards settle) leaves shards unassigned. One node at a time, wait for green/yellow-equilibrium, continue.
4. **Master-eligible nodes follow the same one-at-a-time discipline** but for quorum, not shards: never restart enough masters at once to lose majority, and prefer upgrading data nodes before final master cutover per Elastic's upgrade sequencing.

## Keeping the data safe while the fleet churns

1. **PVCs survive rolling updates by design.** During a rolling update a pod is recreated *with its existing PVC reattached* — deletion of claims only happens via the retention policy on scale-down or set deletion, not from pod replacement or node failure. Know this before someone "fixes" data loss that was never going to happen.
2. **Set `persistentVolumeClaimRetentionPolicy` deliberately (stable since v1.32).** The common production shape is `whenDeleted: Retain` / `whenScaled: Delete` — keep data if the set is deleted (fat-finger insurance), reclaim it on scale-down (cost control). Defaults are `Retain`/`Retain`, so scaled-down stateful sets silently hoard volumes (an infrastructure-cost-tagging.md line item).
3. **Pre-deploy backups still apply, per cluster not per pod.** A fleet upgrade is a maintenance window in disguise: snapshot/backup before the first hop (pre-deploy-database-backup.md), because rollback of a stateful upgrade may mean restoring data, not just pod specs.
4. **Soak between ordinals on schema-format-sensitive upgrades.** Storage-format and on-disk format changes are frequently one-way: once a broker/index has upgraded its segments, the old version cannot read them back. For those releases, "rollback" is restore-from-backup — which is exactly why those upgrades deserve a game-day rehearsal first, and why the soak gate between hops should be long enough to catch consumer lag and replication lag before the fleet passes the point of no return.
