# Kubernetes Job pod replacement policy

**Issue:** Replacing a terminating Job Pod immediately can temporarily exceed desired parallelism and duplicate expensive or non-idempotent work.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Select `.spec.podReplacementPolicy` based on workload semantics. `Failed` waits for the previous Pod to terminate before replacement and is required with pod failure policy; `TerminatingOrFailed` favors faster replacement. Make work idempotent, use durable attempt identifiers, and include termination grace time in capacity and deadline calculations. Do not infer completed work merely from deletion timestamps.

## Verification

Create a controlled long-termination case and measure active plus terminating Pods, replacement latency, and duplicate side effects for each policy. Verify failure-policy compatibility through server-side validation on the target cluster version.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/job-v1/)
