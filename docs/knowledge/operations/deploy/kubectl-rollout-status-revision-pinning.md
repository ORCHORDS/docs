# Kubectl rollout status revision pinning

**Issue:** A deployment verification job that watches only the latest rollout can silently switch to a newer revision started by another actor and report success for code it did not deploy.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Capture the deployment revision created by the release and call `kubectl rollout status` with `--revision=N` and a finite `--timeout`. Serialize production mutation where possible, annotate releases with immutable build identity, and fail when the watched revision is superseded. Follow rollout completion with application-level health and smoke tests.

## Verification

Trigger a second rollout in a staging race test and confirm the first job aborts rather than following the new revision. Verify timeout failure, deployment conditions, pod readiness, and immutable artifact identity. Preserve all admission, test, and security gates.

## Gotchas

Revision pinning protects attribution but does not prove request-path health. Revision numbers depend on rollout history and should be captured from the target cluster, not guessed.

## Official sources

- https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_status/
- https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
