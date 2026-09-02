# Open Policy Agent Policy-as-Code Platform Governance

## Purpose

Govern the use of Open Policy Agent (OPA) and Rego-based policy engines (including CNCF-ecosystem admission controllers like Kyverno that express policy as code) so that platform policy — admission control, authorization, and configuration policy — is expressed as versioned, tested code with deliberate scoping, rather than as scattered imperative checks or tribal rules.

## Scope

Applies to every OPA (or Rego/Kyverno-class) policy deployment in studio platforms: Kubernetes admission control, API authorization, CI/CD gating, and data filtering. Covers policy authoring lifecycle, testing, deployment, and evaluation monitoring. Does not cover the policy content of specific compliance regimes.

## Workflow

1. Express platform policy as code in version control: every admission rule, authorization decision, and gate is a Rego module or policy document with an owner and change history; policy configured only through consoles or APIs is drift and is flagged.
2. Scope each policy deployment deliberately: an OPA instance serves a defined decision domain (admission for cluster X, authorization for service Y); catch-all policy servers without scope boundaries are prohibited.
3. Test policies as code: each policy ships with unit tests covering permit, deny, and edge cases, and CI runs them against the policy's data fixtures; untested policies do not merge.
4. Manage policy data separately from policy logic: bundle or distribute data (allowlists, role mappings) with its own versioning and refresh cadence; conflating data changes with logic changes obscures audit.
5. Deploy policies through the same GitOps flow as workloads: policy changes roll out with review, staged environments, and rollback capability.
6. Monitor decision outcomes: allow/deny rates per policy, evaluation latency, and error rates are exported; a silent policy engine is an unobserved control.
7. Audit decision trails: decision logs (or admission logs) retained for the audit window with enough context to reconstruct why a request was permitted or denied.

## Controls and evidence

- Policy repository with owner, tests, and change review records per policy module.
- Deployment scope documentation per OPA/policy-engine instance.
- CI test results for policy modules, including edge-case coverage.
- Decision monitoring dashboards and alerting configuration.
- Decision log retention configuration meeting the audit window.

## Validation

- Sample 10 deployed policies and confirm each has unit tests that ran in CI at its current revision.
- Confirm decision monitoring shows allow/deny rates and latency for each policy deployment.
- Reconstruct one production decision from decision logs and confirm the trail is sufficient.

## Failure correction

- **Untested policy deployed** → roll back or emergency-review, add tests, and gate future merges on test presence.
- **Decision monitoring silent** → restore metrics export, and review decisions made during the blind window from logs.
- **Policy drift from version control** → reconcile from Git, and investigate the console or API path that bypassed the flow.

## Limitations

- Policy engines decide what they are asked: the integration points (which requests reach OPA) are the real control boundary and need separate validation.
- Rego evaluation performance depends on data size and query shape; monitor latency, not just correctness.
- Multiple policy systems (OPA, Kyverno, cloud-native IAM) can overlap; document which system owns which decision to avoid conflicting allows.

## Scope note

This article is part of the platforms leaf. Cross-reference: `OPEN_POLICY_AGENT_GATEKEEPER_ADMISSION.md` if present, `infra/kubernetes-admission-controller-chain-design.md` (operations leaf), and `CNCF_TEKTON_PIPELINE_SUPPLY_CHAIN_GOVERNANCE.md` (operations leaf).

## Canonical sources

- Open Policy Agent — Documentation: https://www.openpolicyagent.org/docs/
- OPA — Rego policy language: https://www.openpolicyagent.org/docs/latest/policy-language/
- CNCF — Kyverno documentation: https://kyverno.io/docs/
- Kubernetes — Dynamic Admission Control: https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/
- CNCF — Graduated and incubating projects: https://www.cncf.io/projects/
