# Flux Kustomization dependency readyExpr contract

**Issue:** A Flux dependency can report Ready while it is the wrong application version, or a custom `readyExpr` can accidentally replace the controller's built-in readiness check and unblock an unsafe rollout.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `.spec.dependsOn` for real reconciliation ordering and health, not as a substitute for application-level compatibility.
- Add `readyExpr` only when the dependency needs a narrow CEL invariant such as lockstep version labels. Keep the expression reviewable and limited to the available `dep` and `self` objects.
- By default, a custom readiness expression replaces the built-in dependency check. Enable and test `AdditiveCELDependencyCheck` only when both checks are required by policy.
- Pair dependency readiness with `.spec.wait` or explicit health checks on the dependency, and avoid circular dependency graphs.
- Version labels used by the expression must be immutable deployment inputs, not values a workload can edit.

## Verification

Test matching and mismatching versions, dependency Unknown/False, missing labels, malformed CEL, controller restart, stale source revision, and a deliberate cycle. Assert the dependent Kustomization remains blocked until every required check passes, then verify the exact reconciled revisions.

## Gotchas

- Reconciliation order does not make two applications transactionally atomic.
- An expression that returns true too broadly removes the safety the dependency was meant to provide.
- Health-check success can lag or outlive the business capability it approximates.

## Official source

- [Flux Kustomization dependencies and readyExpr](https://fluxcd.io/flux/components/kustomize/kustomizations/#dependency-ready-expression)
