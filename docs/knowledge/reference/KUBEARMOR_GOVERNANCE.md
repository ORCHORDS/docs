---
title: KubeArmor Container-Aware eBPF Policy Engine Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://kubearmor.io ; https://github.com/kubearmor/KubeArmor
---

# KubeArmor Container-Aware eBPF Policy Engine Version Governance

## 1. Purpose

This reference card governs the deployment and upgrade model for KubeArmor, a CNCF Sandbox observability and policy enforcement engine that attaches LSM (Linux Security Module) hooks via eBPF and translates Kubernetes-native `SecurityPolicy` resources into kernel-level constraints. It applies to clusters that require per-container process, file, network, and capability hardening on top of Pod Security Standards.

## 2. Scope

In scope:

- KubeArmor **DaemonSet** (relay + kubearmor) and **karmor** CLI ≥ 1.7.
- `KubeArmorPolicy` and `KubeArmorHostPolicy` CRDs (apiVersion `security.kubearmor.com/v1`).
- AppArmor, SELinux, and BPF LSM backend selection.
- Integration with Tetragon for kernel-level visibility and with OPA/Gatekeeper for declarative cluster policy.

Out of scope:

- Pure userspace seccomp profiles (`securityContext.seccompProfile`) — handled separately.

## 3. Versioning policy

- Pin the **KubeArmor DaemonSet** to a specific Helm chart revision (e.g. `1.7.6`) and a specific container image digest; never float on `:latest`.
- Pin the **BPF LSM** object to the kustomize overlay that matches the deployed `kubearmor/kubearmor` version. Mixing versions causes dangling map references.
- Require kernel ≥ 5.4 for BPF LSM; fall back to AppArmor on 4.19 LTS nodes.

## 4. Compatibility matrix

| KubeArmor | k8s minimum | kernel | BPF LSM | AppArmor | SELinux | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1.5.x | 1.25 | 4.19 LTS | opt-in | yes | yes | LSM coexistence flag required |
| 1.6.x | 1.27 | 5.4 LTS | opt-in | yes | yes | HostPolicy CRD GA |
| 1.7.x | 1.29 | 5.10 LTS | opt-in (default) | yes | yes | Network egress policy (Cilium CNI) |

## 5. Policy authoring

- Use `KubeArmorPolicy` (namespaced) for in-pod allow-listing. Default to `Action: Block` with `Severity: <1-10>`.
- Use `KubeArmorHostPolicy` only for node-level constraints; restrict to operators with the `kubearmor:hostpolicy` RBAC role.
- Always supply `Selector.identifiers` for the policy; policies without a selector that match by namespace alone are flagged at admission.

## 6. Upgrade procedure

1. Drain one node, apply the new DaemonSet, and validate with `karmor vm --all-namespaces` that policy enforcement matches the previous behaviour on a canary workload.
2. Roll forward one node-pool at a time. Watch `kubearmor_violations_total{policy=...}` for regressions.
3. Promote to all pools after 24 h with no alert increase on `KubeArmorPolicyViolation` events.

## 7. Rollback procedure

- `helm rollback kubearmor <previous-revision>` reverts the chart to the pinned revision.
- If a policy CRD schema breaks, scale the DaemonSet to zero first, then revert the CRDs, then redeploy.

## 8. Observability

- Required metrics: `kubearmor_policy_alerts_total{policy,action,severity,namespace}`, `kubearmor_violations_total{policy,operation}`, `kubearmor_enforcer_status{kind=block|audit}`.
- Alert on `sum(rate(kubearmor_policy_alerts_total{action="Block"}[5m]))` crossing platform-specific thresholds.
- Stream alerts to a SIEM via the KubeArmor relay → syslog/Kafka exporter.

## 9. References

- KubeArmor documentation — https://docs.kubearmor.io
- KubeArmor GitHub releases — https://github.com/kubearmor/KubeArmor/releases
- BPF LSM kernel documentation — https://docs.kernel.org/bpf/prog_lsm.html
