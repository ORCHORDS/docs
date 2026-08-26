# singleton-service-leader-election-deploys

**Issue:** Some services must run exactly once: schedulers, cron-style pollers, queue consumers with non-idempotent handlers, agent fleet coordinators, ledger reconcilers. Deploying them with the standard rolling-update playbook silently creates two of them mid-rollout — the old pod still holds a timer while the new pod starts firing its own — producing duplicate sends, double charges, and duplicated agent runs. Deploying them as single-replica Deployments instead trades duplication for unavailability and a crash-loop window during rollout. The fix is running multiple replicas behind leader election and making deploys lease-aware.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why single-replica deployments fail

1. **Rolling updates require overlap.** A Deployment with replicas: 1 and a RollingUpdate strategy must start the new pod before stopping the old one (maxUnavailable semantics), so for a window both are scheduled. For a stateless API that overlap is harmless; for a singleton it is two schedulers running the same jobs. Only the Recreate strategy avoids overlap, at the cost of a hard outage during every deploy.
2. **Crash loops are outages.** With one replica, an OOM kill or node drain takes the service to zero until rescheduling. Availability for singletons comes from standby replicas that can take over, which only exists if the service supports multiple live processes coordinating.
3. **Node maintenance deploys you involuntarily.** Cluster autoscaler or upgrades evicting the single pod is a deploy you did not schedule. Leader-elected multi-replica singletons survive eviction by failing over to a standby.

## The leader election pattern

1. **Run N replicas, elect one leader.** Deploy the singleton as a multi-replica Deployment where every replica runs the same code, but only the current leader executes scheduled work; standbys stay warm and ready. This is the standard client-go leaderelection pattern documented in the Kubernetes examples and the k8s.io/client-go/tools/leaderelection package.
2. **Use Lease objects, not ConfigMaps or Endpoints.** Current best practice is LeaseLock (coordination.k8s.io/v1 Lease): it is purpose-built, lightweight, and has explicit renewal semantics. ConfigMap and Endpoints-based locks are legacy approaches that survive in old blog posts; new implementations should not copy them.
3. **Release the lease on SIGTERM.** The leader's shutdown handler must give up the lease (or stop renewing and exit promptly) so a standby acquires leadership in seconds rather than waiting out the full lease deadline. This is what makes rolling updates of singletons fast instead of minute-long stalls.
4. **Set lease timing for your deploy cadence.** LeaseDuration, RenewDeadline, and RetryPeriod control failover speed versus false takeovers. A common starting point is 15s/10s/2s: failover inside roughly one lease duration, tolerant of transient API-server hiccups. Faster failover tightens deploys but risks split-brain during API-server slowness.
5. **Non-leaders must be ready.** Standby pods should pass readiness so the Deployment considers them available; leadership is application state, not pod state. Readiness that depends on being leader breaks rollout math.

## Making the deploy itself safe

1. **Terminate the leader first is fine — with drain semantics.** During a rolling update, Kubernetes may kill the current leader. The SIGTERM path (release lease, finish or hand off the in-flight job) turns that into a brief failover. Ensure terminationGracePeriodSeconds exceeds your longest in-flight task, or make tasks resumable, otherwise a killed job is a lost job.
2. **Make jobs idempotent or trackable.** Even with clean lease handoff, the overlap window between lease release and renewal expiry can briefly produce two believers. Guard the work itself: dedupe by job id, take a row lock, or use an outbox marker, so a duplicate execution is a no-op rather than a double charge. Exactly-once delivery does not exist; exactly-once effect must be engineered.
3. **Do not overlap incompatible versions.** A new-version leader and old-version standby must agree on lease semantics and job formats. Version the job payloads the way event schemas are versioned (see event-schema-compat-deploys.md) so a v2 leader never corrupts v1 expectations during the rollout window.
4. **Consider whether you need a custom singleton at all.** If the work is truly cron-shaped, a Kubernetes CronJob may replace a custom scheduler entirely — the control plane already guarantees one concurrent execution per schedule (with concurrencyPolicy guards). Custom leader election earns its complexity only when the service needs continuous coordination, long-running task state, or cross-cluster awareness.
5. **Scale-to-zero workers are a different pattern.** Queue consumers that can safely process concurrently should not be singletons at all — run them horizontally with per-message acknowledgements, and reserve leader election for the irreducibly single coordination point (for example, the dispatcher that enqueues for others).

## Observability and drills

1. **Alert on leadership churn.** Track leader identity and lease transitions as metrics. Frequent failovers during deploys are expected once per rollout; frequent failovers at idle mean a broken renewal loop or API-server latency, and silent standbys mean a dead election loop doing nothing.
2. **Verify exactly-one after every deploy.** Post-deploy smoke checks should assert the singleton acted exactly once on a probe job (send one probe message through the real path, assert single receipt). This is the cheapest guard against the duplicate-execution class of bugs, and it belongs in the same checklist as deployment-verification-smoke-tests.md.
3. **Rehearse lease expiry.** Periodically kill the leader pod outside a deploy window and measure time-to-takeover. The number you get in a drill is the number you will live with during every future rollout and every node failure (see rollback-drills-restore-testing.md for the drill discipline).
