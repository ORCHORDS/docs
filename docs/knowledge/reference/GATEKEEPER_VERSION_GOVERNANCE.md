---
title: OPA Gatekeeper Admission Policy Engine Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://open-policy-agent.github.io/gatekeeper/ ; https://github.com/open-policy-agent/gatekeeper
---

# OPA Gatekeeper Admission Policy Engine Version Governance

## 1. Purpose

This reference card governs the lifecycle of the **OPA Gatekeeper** admission controller — the Rego-based policy engine that validates Kubernetes resources against custom ConstraintTemplates before they are persisted to the cluster.

## 2. Scope

In scope:

- Gatekeeper v3.16+ (apiVersion `templates.gatekeeper.sh/v1`, ConstraintTemplate CRD).
- Validation mode `audit` (warn only), `warn` (advisory event), `enforce` (deny).
- Mutation webhooks (`v1.MutatingAdmissionPolicy`-style features remain out of scope until GA).
- Per-namespace exemption via the `gatekeeper-mutator` exempt namespace annotation.

Out of scope:

- Generic OPA use outside Kubernetes admission (use the OPA CLI / Rego playground).
- Kubewarden (see Batch 103 reference card `KUBEWARDEN_VERSION_GOVERNANCE.md`).

## 3. Versioning policy

- Pin Gatekeeper to a specific minor (e.g. `v3.16.3`) and verify digest against the published SLSA provenance.
- Gatekeeper MUST stay within one minor of upstream Kubernetes (e.g. K8s 1.30 → Gatekeeper 3.16.x).
- Use the **ConstraintTemplates** library, not hand-written mutation policies, for all new policies.
- Each ConstraintTemplate MUST have at least one `c.match` and one `parameters` schema to make the constraint self-documenting.

## 4. Compatibility matrix

| Gatekeeper | K8s | Rego | Notes |
| --- | --- | --- | --- |
| 3.14.x | 1.28+ | v1 | OPA v0.59 |
| 3.15.x | 1.29+ | v1 | Mutation hook GA |
| 3.16.x | 1.30+ | v1 | Multi-version support |
| 3.17.x | 1.31+ | v1 | External data sources stable |

## 5. Authoring policy

- All Rego MUST pass `opa fmt --diff` and `opa test` with ≥ 90% rule coverage.
- Avoid embedding business policy in Rego; reference an external data source (`externaldata.gatekeeper.sh`).
- Tag every constraint with `metadata.labels.policy-source` so audit reporting can group policies.
- Disable the default empty `K8sPSP` constraint library; we do not use PodSecurityPolicy.

## 6. Rollout procedure

1. New policy: apply ConstraintTemplate + Constraint in `audit` mode; collect `audit-results` for 14 days.
2. Move to `warn`; verify cluster events show warnings but no denies.
3. Promote to `enforce`; capture `kubectl get k8srequiredlabels` for proof.
4. Document exemption namespaces and rationale in `policies/gatekeeper/exemptions.md`.

## 7. Upgrade procedure

1. Read the release notes for CRD schema changes.
2. Apply `kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/release-3.16/deploy/gatekeeper.yaml` against a staging cluster.
3. Validate that existing constraints continue to compile.
4. Promote after 7 days of clean audit results.

## 8. Rollback procedure

- `kubectl rollout undo deployment/gatekeeper-controller-manager -n gatekeeper-system`.
- Existing constraints remain valid because the API is backward compatible within one minor.

## 9. Observability

- Required metrics: `gatekeeper_controller_runtime_reconcile_total{status}`, `gatekeeper_violations{constraint,enforcement_action,resource_kind}`, `gatekeeper_constraint_template_evaluation_seconds_bucket{constraint}`.
- Alert on `gatekeeper_violations{enforcement_action="deny"}` > 100/min (sustained 5 min).

## 10. References

- Gatekeeper docs — https://open-policy-agent.github.io/gatekeeper/website/docs/
- ConstraintTemplate library — https://github.com/open-policy-agent/gatekeeper-library
