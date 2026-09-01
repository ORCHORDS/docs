# Flux Kustomization Health Checks

**Issue:** Flux reconciles from Git continuously, but a Kustomization that reports Ready=True without verifying application-level health will greenlight a release whose pods are crashlooping or whose service is unreachable. Flux v2 provides health checks at both the resource and Kustomization levels, and the practical difference between those two layers is where most teams lose their footing.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Resource Health And Kustomization Health

Flux inherits resource health checks from `kube-status-metrics`, which classifies a Kubernetes resource as Healthy, Progressing, or Degraded based on its status fields and a kind-specific health Lua script shipped with the controller. A Kustomization's overall readiness is the aggregate of its resource health checks plus a reconciliation gate. A Kustomization that has applied every resource correctly but whose pods are crash-looping still reports Ready=False because the resource-level health check has not yet flipped to Healthy.

The two layers serve different purposes. Resource health answers "is this resource in its desired state?". Kustomization health answers "did the last reconciliation succeed and are all resources healthy?". A misconfigured Kustomization that references a missing source will fail the Kustomization health check immediately, before any resource is applied. A Kustomization that applied successfully but whose pods are crashing will pass the reconciliation check and fail the resource health check. Both states must be observable.

## Configuring The Health Check Endpoint

Flux's Kustomization CRD exposes a `healthChecks` field under `.spec`, although the more common configuration is to rely on the bundled health checks and add custom checks via `HealthCheck` resources. A `HealthCheck` resource targets a specific GroupVersionKind and declares an `apiVersion` and a `kind` plus a Lua expression that examines the resource's status fields. The expression returns a HealthCheckResult whose Outcome is Healthy, Progressing, or Degraded.

When writing a custom check, start from a known-good example shipped with the GitOps Toolkit and modify one field at a time. The bundled checks for Deployment, StatefulSet, and DaemonSet have been validated against many real-world resource shapes, so re-implementing them from scratch is rarely needed. Add a custom check only when the bundled check produces a known wrong answer for a specific resource shape, and document the rationale in the repository.

## Negative Conformance Tests

The most reliable way to validate a health check is a test that injects a known broken resource and asserts the Kustomization reports Degraded. The test runs against a kind cluster or a CI namespace and uses a simple pattern: apply a Deployment with an invalid image, observe the Kustomization within a timeout, assert the readiness condition flipped to False with a reason that points at the failed resource. Without this test, the health check passes unit tests but fails silently in production.

Negatives also catch the failure mode where the health check expression is too lenient. A Lua check that returns Healthy whenever a field exists will report Healthy even when the field's value indicates failure. The test should construct a resource whose status field is present and incorrect, and verify the check returns Degraded. The test resource can live in a `testdata/` directory inside the GitOps repository and run on every PR.

## Suspended And Ready Conditions

A Kustomization can report Ready=True and be suspended at the same time; this is by design, because suspension is a separate concern from reconciliation health. The `spec.suspend` field halts reconciliation but does not reset the ready condition; a previously reconciled Kustomization remains Ready while suspended. Teams that rely on the Ready condition alone to decide whether a release is current will mistakenly report a suspended Kustomization as up-to-date.

The correct operational signal is the reconciliation status from `kubectl get kustomization -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'` combined with `lastAppliedRevision` and `lastAttemptedRevision`. If the two revisions differ, the Kustomization is either progressing or stuck, regardless of Ready. Use a dashboard that surfaces all three signals, and alert when Ready=True but the revision has not advanced within the configured interval.

## Failure Modes

The most common failure is treating the bundled health checks as infallible. They are Lua scripts that depend on the resource shape matching the script's expectations; if the upstream API introduces a new status field that the script does not consider, the script may misclassify. Run a periodic test that exercises every supported Kind with a canonical healthy and broken fixture, and refresh the bundled checks when upgrading Flux.

A second failure is layering custom health checks on top of each other without understanding the order. Flux evaluates health checks in a defined order, and a permissive check can mask a stricter check. The order is documented in the GitOps Toolkit source; consult it before adding custom checks. If two checks disagree, the more restrictive outcome wins, but the logs may only show the final outcome, hiding the disagreement from operators.

A third failure is health checks for resources that the Kustomization does not own. A health check applied to a cluster-scoped resource that multiple Kustomizations reconcile will fail when any one of them applies a broken version, even if the others are healthy. Scope health checks to the Kustomization via the `HealthCheck` resource's namespace selector and avoid health checks for resources that cross Kustomization boundaries.

## Canonical sources

1. https://fluxcd.io/flux/components/kustomize/kustomizations/
2. https://fluxcd.io/flux/components/kustomize/healthchecks/