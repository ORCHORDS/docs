# KubeArmor Hard Policy Rollout Playbook

## Purpose

Provide a controlled, observable rollout procedure for transitioning a Kubernetes namespace from audit-only KubeArmor policies to hard-blocking policies without service disruption.

## Audience

Platform engineers, security engineers, SRE on-call.

## Pre-conditions

- KubeArmor ≥ 1.7 deployed on all target nodes.
- `KubeArmorPolicy` and `KubeArmorHostPolicy` CRDs present.
- A test environment that mirrors production network and storage characteristics.
- Sign-off from the service owner for the target namespace.

## Procedure

1. **Baseline**: deploy the policy in `Audit` mode only; allow at least 7 calendar days of observation.
2. **Tune**: review `kubearmor_violations_total` by `severity` and `operation`. Investigate any unexpected allow-list hits — these are usually missing base-image permissions or health-probe file paths.
3. **Shadow**: switch the policy to `Audit` with `Severity: 8..10` triggers a Slack alert; lower severities remain logged.
4. **Soft block**: change `Action: Audit` to `Action: BlockSoft` for the lowest severity tier first; observe error budgets for 3 days.
5. **Hard block**: change `Action: Block` and pin the policy. Watch SLO dashboards for at least one full business cycle before promotion.
6. **Codify**: commit the policy YAML to the platform repo; configure a `Kustomize` patch that applies it to every new namespace in the `prod-*` label set.
7. **Document**: link the policy YAML hash and rollout PR in `policies/kubearmor-rollouts.md`.

## Rollback

- Switch `Action` back to `Audit`. KubeArmor reloads in under 60 seconds per node. Confirm `kubearmor_enforcer_status{kind="audit"} == 1` cluster-wide before leaving the change open.
- If the policy CRD itself is suspect, delete it and rely on the next reconciler pass to recreate from the platform repo.

## References

- KubeArmor policy reference — https://docs.kubearmor.io/kubearmor-policies/
- NIST SP 800-204C — implementation of DevSecOps for systems-of-systems (see Batch 98 standards card).
- CIS Kubernetes Benchmark v1.9 §6 (Pod Security) and §3 (Policies).
