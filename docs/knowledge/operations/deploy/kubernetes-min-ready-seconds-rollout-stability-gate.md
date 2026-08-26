# Kubernetes minReadySeconds as a rollout stability gate

**Issue:** A rollout can appear successful when a new Pod becomes Ready briefly and then crashes, allowing unstable replicas to advance deployment state.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Set `.spec.minReadySeconds` when a workload must remain Ready and crash-free for a minimum observation window before Kubernetes considers the Pod available. This is distinct from readiness probes: the probe establishes current readiness, while `minReadySeconds` requires readiness to remain stable long enough to count toward Deployment availability.

Coordinate the value with `.spec.progressDeadlineSeconds`; Kubernetes requires the progress deadline to be greater than `minReadySeconds`. Select both from measured startup, warm-up, and failure-detection times rather than copying a universal value.

## Operational controls

- Make readiness probes represent actual traffic-serving ability.
- Keep `minReadySeconds` long enough to expose common early failures but short enough to preserve deployment velocity.
- Make the progress deadline include image pull, scheduling, startup, readiness, and the stability window.
- Monitor Deployment conditions and fail automation on `ProgressDeadlineExceeded`; Kubernetes reports the condition but does not automatically roll back.
- Test interactions with `maxSurge`, `maxUnavailable`, resource quotas, and Pod disruption controls.

## Verification

1. Deploy a healthy revision and confirm it is not counted Available until the stability window passes.
2. Deploy a revision that becomes Ready and then crashes within that window; confirm it never advances availability.
3. Run `kubectl rollout status` with an explicit timeout and verify CI receives a non-zero result for a failed rollout.
4. Inspect Deployment conditions and ReplicaSet state before deciding whether to roll back.

## Sources

- [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes: Configure liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
