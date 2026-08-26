# Kubernetes startup-probe budget and probe separation

**Issue:** Slow-starting applications can be killed by liveness checks before initialization, while oversized startup budgets hide permanent failures.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

A startup probe suppresses liveness and readiness probing until it succeeds. Its failure threshold and period define the startup budget. Keep startup, readiness, and liveness endpoints semantically distinct: started, able to receive traffic, and able to recover only by restart.

## Controls and verification

- Set the budget from measured cold starts plus bounded variance.
- Do not make readiness depend on every optional downstream service.
- Keep liveness checks cheap and local.
- Alert before repeated startup failure becomes a silent restart loop.
- Test cold storage, migration, and dependency-delay scenarios.
- Verify an irrecoverable startup failure is killed after the intended budget.

## Sources

- [Kubernetes: Configure probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Kubernetes: Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
