# Kubernetes PDB Unhealthy-Pod Eviction Policy

**Issue:** A PodDisruptionBudget can block node drain when selected Pods are running but unready, leaving operators unable to remove a failed node or complete maintenance.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Choose `spec.unhealthyPodEvictionPolicy` explicitly:

- `IfHealthyBudget` protects running-but-unready Pods unless the application still meets its desired healthy count. It is the default.
- `AlwaysAllow` lets eviction proceed for running-but-unready Pods while healthy Pods remain protected by the budget.

Use `AlwaysAllow` only when the workload can recreate an unhealthy replica elsewhere and does not depend on irreplaceable node-local state. Keep the conservative policy for workloads where even an unhealthy Pod may be the only recoverable copy.

## Controls

- Ensure Deployment/StatefulSet readiness probes represent service availability.
- Use a selector that matches exactly the intended controller; an empty selector in policy/v1 selects every Pod in the namespace.
- Set either `minAvailable` or `maxUnavailable` from a documented availability objective.
- Check controller replica count, scheduling capacity, topology constraints, and storage attachment before drains.
- Run `kubectl drain --dry-run=server` or an equivalent eviction preflight in maintenance automation.
- Alert on `disruptionsAllowed=0` that persists while nodes require maintenance.

## Verification

Create one unhealthy replica in staging, then test Eviction API behavior for both policies. Confirm a healthy replica is never evicted beyond the budget, the unhealthy replica reschedules, readiness recovers, and traffic stays inside the error budget. Test multi-zone loss and insufficient-capacity scenarios; the policy cannot create capacity.

## Gotchas

PDBs govern voluntary disruptions through the Eviction API, not every deletion or involuntary failure. Direct Pod deletion can bypass the intended workflow. A permissive unhealthy policy helps drains but can accelerate loss if readiness is faulty, so probe validation is part of the change.

## Sources

- [Kubernetes PodDisruptionBudget API](https://kubernetes.io/docs/reference/kubernetes-api/policy-resources/pod-disruption-budget-v1/)
- [Kubernetes disruptions and PodDisruptionBudgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
