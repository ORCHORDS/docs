# Kubernetes per-container restart-rule rollout

**Issue:** A Pod-wide restart policy cannot distinguish retriable exit codes from permanent failures for individual containers.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

On Kubernetes v1.35, verify the beta `ContainerRestartRules` feature is enabled across API servers and kubelets before using container-level `restartPolicy` and ordered `restartPolicyRules`. Maintain a documented exit-code contract and fall back deliberately to the container policy when no rule matches. Do not apply rules to native sidecars, which do not support them.

## Verification

Test every declared exit code, unmatched codes, kubelet restart, exponential backoff, mixed-version nodes, and init-container behavior. Admission must keep workloads off nodes lacking the feature.

## Gotchas

- Pin and test the exact supported version; defaults and feature states can change.
- Preserve reproducible evidence without storing secrets or personal data.
- Define rollback before production rollout.

## Official source

- [Primary documentation](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#individual-container-restart-policy-and-rules)
