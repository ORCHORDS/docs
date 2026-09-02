# CNCF KubeArmor License Audit Governance

## Purpose

KubeArmor (CNCF Incubating) is a runtime security enforcement system that uses Linux security modules (AppArmor, BPF-LSM) to constrain pod, container, and host behavior. The license-audit governance pattern captures the policy distribution process, the KubeArmor enforcement modes (audit, block), the BPF program version, the per-namespace policy scope, and the documented exceptions. Without explicit governance, KubeArmor policies drift across namespaces and enforcement gaps appear silently.

## Current context and source status

KubeArmor 1.4 (released 2024) and KubeArmor 1.5 (released 2025) are the current supported versions. KubeArmor 1.6 entered beta in 2026. The project follows the CNCF Incubating governance model. KubeArmor supports AppArmor, BPF-LSM, and SELinux enforcement modes; BPF-LSM requires Linux kernel 5.8+.

## Governance pattern

1. Pin KubeArmor version and enforcement mode in cluster bootstrap.
2. Use `audit` mode for initial rollout; switch to `block` after observing zero false positives for a documented period.
3. Scope policies by namespace using `KubeArmorPolicy` selectors (`selector.matchLabels`).
4. Distribute policies via GitOps; reject ad-hoc `kubectl apply` outside the change window.
5. Maintain a policy exception register with justification, owner, and expiry.
6. Monitor KubeArmor metrics: `kubearmor_alerts`, `kubearmor_containers_monitored`, `kubearmor_host_policy_status`.
7. Alert on enforcement violations to the documented escalation chain.
8. Test policies against known-benign workloads before promoting to `block` mode.
9. Document the rollback procedure: switch enforcement mode to `audit`, observe, remediate, re-enable `block`.
10. Reconcile KubeArmor policies with Kyverno admission policies to avoid conflicting decisions.

## Validation and evidence

- KubeArmor version and enforcement mode recorded in cluster inventory.
- Policy distribution via GitOps.
- `audit` mode baseline recorded (violation count per day, top 10 violators).
- `block` mode promotion gate documented.
- Policy exception register reconciled against active exceptions.
- Metrics dashboard deployed and reviewed.

## Failure correction

Common defects include switching to `block` mode without an `audit` baseline, missing namespace selectors causing cluster-wide impact, and orphan exceptions without expiry. Corrective actions include requiring `audit` baseline before `block` promotion, narrowing selectors, and enforcing exception expiry in CI.

## Limitations

- KubeArmor policies do not extend to non-Kubernetes workloads.
- BPF-LSM requires kernel 5.8+; AppArmor is the fallback.
- KubeArmor does not provide network policy (use Cilium or Calico).
- Policy changes do not affect already-running workloads without a restart.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (KubeArmor deployment topology), **security** (runtime enforcement and policy), **engineering** (BPF-LSM and AppArmor profiles), and **templates** (KubeArmor policy template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- KubeArmor documentation (CNCF Incubating): https://www.kubearmor.io/docs/
- KubeArmor GitHub repository (CNCF Incubating): https://github.com/kubearmor/KubeArmor
- KubeArmor policy reference (CNCF Incubating): https://www.kubearmor.io/docs/policy/

Sources were verified on September 1, 2026.