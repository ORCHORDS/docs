# Kubernetes Indexed Job success policies

**Issue:** Distributed batch work may wait for every index even when a valid quorum or leader result is already sufficient.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

For Indexed Jobs, define immutable `.spec.successPolicy.rules` using explicit succeeded indexes and/or counts. Document why early success is correct for the algorithm, because the controller terminates lingering Pods after success criteria are met. Evaluate failure and success policies together: a terminating failure policy can win before success. Keep result durability outside Pod lifetime so early cleanup cannot erase the accepted output.

## Verification

Test the minimal successful index set, partial success outside the accepted set, competing failure criteria, and graceful termination of remaining Pods. Assert the final conditions include success criteria and completion, and verify the artifact is complete before acknowledging the Job.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://kubernetes.io/docs/concepts/workloads/controllers/job/#success-policy)
