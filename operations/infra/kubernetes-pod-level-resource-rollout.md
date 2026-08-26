# Kubernetes pod-level resource rollout controls

**Issue**

Pod-level resource requests and limits change scheduling and cgroup budgeting semantics relative to container-only declarations, so an unmeasured migration can alter placement, throttling, and policy enforcement.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Confirm feature availability on the pinned cluster version and admission stack.
- Canary one workload class; retain container requests for critical sizing until measurements prove equivalence.
- Update quota, LimitRange, autoscaling, and policy checks to understand pod-level fields.
- Budget init and sidecar behavior explicitly.

## Verification

1. Compare scheduled nodes, QoS class, cgroup files, throttling, OOM events, and HPA signals.
2. Exercise burst sharing between containers within the pod budget.
3. Test admission on mixed-version clusters.

## Gotchas

- Pod-level budgets do not make per-container hotspots harmless.
- Schedulers and external policy engines may gain support at different times.
- Metrics pipelines may initially report only container resources.

## Official source

- [Official documentation](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
