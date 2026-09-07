# Cosign Image Signing and Verification Rollout Playbook

## Purpose

Roll out Sigstore cosign image signing in CI and cosign signature verification at the Kubernetes admission boundary under the version, keyful/keyless, and bundle-format constraints in `COSIGN_VERSION_GOVERNANCE.md` without breaking existing image deploys.

## Audience

Platform engineers, security engineers, and release engineers responsible for the CI pipeline and the Kubernetes admission boundary.

## Pre-conditions

- A supported Kubernetes release under `KUBERNETES_VERSION_GOVERNANCE.md`.
- The target verification stack — Sigstore `policy-controller` or Kyverno with the cosign verification plugin — is reachable from every cluster node.
- A signing strategy (keyful or keyless with Fulcio + Rekor) is documented and approved; see `COSIGN_VERSION_GOVERNANCE.md`.
- A registry (OCI 1.1+) that supports the referrers API is in use; OCI 1.0 registries require an alternative tag schema that this playbook does not cover.

## Procedure

### Step 1 — Choose the signing mode

- Keyful: signing key in a KMS, HSM, or encrypted file. Use for air-gapped environments or where the OIDC issuer is unavailable.
- Keyless (recommended for OIDC-enabled CI): Fulcio issues a short-lived certificate bound to the OIDC identity; Rekor provides the transparency log entry.
- Document the mode and the KMS / OIDC issuer in the runbook and reference the `COSIGN_VERSION_GOVERNANCE.md` minor that supports the chosen mode.

### Step 2 — Pin cosign and policy-controller versions

- Pin cosign to a supported minor (current or N-1) in CI.
- Pin `policy-controller` (or the Kyverno cosign plugin) to the minor that matches cosign bundle-format support.
- Confirm bundle-format version parity: cosign bundle v0.3 must be verified by `policy-controller` ≥ v0.10.
- Validate the bundle layout end-to-end against a single test image before proceeding.

### Step 3 — Sign images in CI

- Run `cosign sign` immediately after the image is pushed; do not sign retroactively from outside CI.
- For keyful signing, the KMS access identity MUST be the CI runner identity; never share a signing key across runners.
- For keyless signing, set `COSIGN_EXPERIMENTAL=1` only when required; pin the Fulcio root CA certificate and use the published transparency log mirror.
- Tag the signature, the SBOM, and the SLSA provenance with the same image digest.

### Step 4 — Stage admission verification (audit)

- Configure `policy-controller` (or Kyverno) in audit-only mode first; admission requests are not blocked but are logged with their verification outcome.
- Run representative workloads for at least 24 hours.
- Triage every audit event that is not "verified": unsigned, signed-but-untrusted-identity, signature-expired, or Rekor-index-missing.

### Step 5 — Promote to enforced admission

- Switch the admission policy from audit to enforce; unsigned or untrusted images are rejected.
- Document the rejection text and the operator's remediation (rebuild and re-sign, exchange identity, update trust policy).
- Confirm the rejection is observable in the platform's audit pipeline; see `NIST_SP_800_92_LOG_MANAGEMENT_GOVERNANCE.md`.

### Step 6 — Verify the trust policy

- The trust policy MUST declare `trustedIdentities` for keyless verification or the KMS certificate root for keyful verification.
- Reject trust policies with `insecureSkipVerify: true` or with empty `trustedIdentities`.
- Pin the Fulcio root CA certificate and the Rekor public key to the exact bytes used by CI; document the rotation schedule.

### Step 7 — Operational handoff

- Hand off the runbook to the on-call rotation with: the KMS access path, the OIDC issuer URL, the `policy-controller` configuration, and the trust policy location.
- Validate the rollback command: returning to permissive admission by toggling the ClusterImagePolicy from `enforce` to `warn`.

## Rollback

- Toggle `policy-controller` (or Kyverno) from `enforce` back to `warn`; admission returns to permit with audit logging.
- If a CI signing outage occurs, fall back to the keyful signing path documented in the runbook; do NOT bypass signing.
- If the `policy-controller` rejects signatures that the CI signed successfully, downgrade `policy-controller` to the previous minor that matches the CI cosign minor.

## References

- `COSIGN_VERSION_GOVERNANCE.md`
- `NOTARY_V2_VERSION_GOVERNANCE.md` — for broader artifact attestation
- `KUBERNETES_VERSION_GOVERNANCE.md`
- `NIST_SP_800_53_R5_SCRM_OVERLAY_GOVERNANCE.md` — for SR-4 provenance
- `NIST_SP_800_92_LOG_MANAGEMENT_GOVERNANCE.md` — for audit retention
- `KYVERNO_POLICY_ROLLOUT_PLAYBOOK.md` — for verification-policy rollout
