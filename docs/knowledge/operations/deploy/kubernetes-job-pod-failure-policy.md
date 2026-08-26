# Kubernetes Job pod-failure policy

**Issue:** Treating every failed Job Pod as the same retryable failure wastes capacity and can retry permanent data or configuration errors until the backoff budget is exhausted.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `podFailurePolicy` only after defining a stable exit-code and Pod-condition contract. Order rules deliberately and select among `FailJob`, `Ignore`, `Count`, and, for indexed Jobs configured accordingly, `FailIndex`. Leave unhandled failures to the documented default rather than assuming they are ignored. Use `restartPolicy: Never` as required by the feature so the Job controller can evaluate terminated containers consistently.

Keep infrastructure disruptions distinguishable from application failures, bound both total and per-index retries, and publish the terminal reason that operators should act on. Validate the API and controller feature state on the exact cluster version before applying manifests.

## Verification

Exercise every declared exit code and condition, an unhandled failure, eviction/disruption, multiple containers, indexed failures, controller restart, and mixed-version nodes. Assert Job conditions, retry counts, failed indexes, events, and alert routing.

## Gotchas

- Rule order is part of the behavior contract.
- Exit codes shared by unrelated failure modes make policies unsafe.
- A retry policy does not make the workload idempotent.

## Official source

- [Kubernetes Job pod failure policy](https://kubernetes.io/docs/concepts/workloads/controllers/job/#pod-failure-policy)
