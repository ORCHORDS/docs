# Kubernetes Deployment progress deadlines and failure triage

**Issue:** A rollout is declared successful because it was applied, while replacement Pods remain unavailable or the Deployment is stalled.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Treat Deployment progress as a release gate. Set a realistic `progressDeadlineSeconds`, wait for the observed revision to become available, and preserve the failed revision, conditions, events, and Pod diagnostics for rollback decisions.

## What the controller reports

A Deployment records a Progressing condition while it creates or scales a new ReplicaSet. When progress exceeds `progressDeadlineSeconds`, Kubernetes reports `ProgressDeadlineExceeded`; this signals controller-observed lack of progress, not automatic rollback.

## Release procedure

1. Pin the intended image digest and capture the Deployment revision before applying.
2. Configure readiness probes and an appropriate progress deadline; do not use a deadline merely to hide slow startup.
3. Wait on the specific Deployment revision and inspect status conditions.
4. On failure, collect ReplicaSet status, Pod scheduling/events, readiness failures, image-pull errors, and resource pressure before changing the manifest.
5. Roll back deliberately to a known revision only after identifying whether the failure is application, configuration, capacity, or dependency related.
6. Re-run smoke checks against the live revision after the controller says it is available.

## Guardrails

- A rollout command returning does not prove the application is serving correct traffic.
- A progress deadline does not replace readiness, end-to-end verification, or alerts.
- Avoid automatically rolling back every deadline exceedance: transient capacity shortages and bad images require different remediation.
- Keep revision history long enough for the approved rollback window.

## Sources

- [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
