---
title: Kubewarden Wasm Policy Engine Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://docs.kubewarden.io/ ; https://github.com/kubewarden/community
---

# Kubewarden Wasm Policy Engine Version Governance

## 1. Purpose

This reference card governs the lifecycle of the **Kubewarden** policy engine — the WebAssembly-based admission controller that runs policies authored in Rego, OPA/Rego, Go, Rust, or TinyGo, packaged as Wasm modules.

## 2. Scope

In scope:

- Kubewarden policy-server v1.20+ and Kubewarden Controller v1.16+.
- Policy types: ClusterAdmissionPolicy, AdmissionPolicy, PolicyServer (CRDs).
- Built-in policies: pod-privileged, pod-host-network, pod-readonly-fs, capabilities-drop-all, allowed-repos, verify-image-signatures, safetynet.
- Wasm modules signed via Sigstore cosign; verification via `SigstoreVerification` configuration.

Out of scope:

- The deprecated Generic Kubernetes Policy Server (legacy).
- The mutation hook (still in beta) is allowed only with an exception.

## 3. Versioning policy

- Pin the policy-server image to a specific patch (e.g. `ghcr.io/kubewarden/policy-server:v1.20.5`) and digest.
- Each PolicyServer MUST run a single Wasm runtime (`wasi`) at a time; mixing runtimes on one server is prohibited.
- Each policy MUST be signed by a trusted OIDC issuer (default: GitHub Actions OIDC via cosign keyless).
- Each PolicyServer MUST have a `replicas` field ≥ 2 for HA.

## 4. Compatibility matrix

| Kubewarden | K8s | Wasmtime | Notes |
| --- | --- | --- | --- |
| 1.16.x | 1.28+ | 18.x | Hostname/namespace-mode policies |
| 1.17.x | 1.29+ | 19.x | PolicyGroup CRD stable |
| 1.20.x | 1.30+ | 21.x | Cosign keyless default |

## 5. Authoring policy

- All policies MUST be published to `oci://ghcr.io/kubewarden/policies/*` and verified via cosign.
- Rego-based policies must pass `kwctl test` with ≥ 80% rule coverage.
- Server-side settings (`settings:` CRD) MUST be validated by a typed schema shipped with the policy.

## 6. Rollout procedure

1. Add a new ClusterAdmissionPolicy with `failurePolicy: Ignore` (audit).
2. Mine audit logs for false positives; refine the policy.
3. Move to `failurePolicy: Fail` (enforce) once 14 days of clean audit.
4. Document in `policies/kubewarden/policy-catalog.md`.

## 7. Upgrade procedure

1. Review the policy-server release notes for new fields.
2. Roll the controller; then roll each PolicyServer one at a time.
3. Validate that existing ClusterAdmissionPolicy resources still reconcile.
4. Promote after 7 days.

## 8. Rollback procedure

- `kubectl rollout undo deployment/kubewarden-controller-manager -n kubewarden`.
- Policies continue to reconcile with the previous policy-server image.

## 9. Observability

- Required metrics: `kubewarden_policy_evaluation_total{policy,mode,result}`, `kubewarden_policy_evaluation_seconds_bucket{policy}`, `kubewarden_wasm_module_size_bytes{policy}`.
- Alert on `kubewarden_policy_evaluation_total{result="error"}` > 0.05 sustained 5 min.

## 10. References

- Kubewarden docs — https://docs.kubewarden.io/
- Policy hub — https://hub.kubewarden.io/
