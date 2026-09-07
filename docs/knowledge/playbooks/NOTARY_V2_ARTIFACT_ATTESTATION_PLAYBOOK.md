# Notary v2 Artifact Attestation Rollout Playbook

## Purpose

Roll out CNCF Notary v2 for signing and verifying OCI artifacts (SLSA provenance, SBOMs, and arbitrary attestation envelopes) under the version, trust-policy, and referrer-binding constraints in `NOTARY_V2_VERSION_GOVERNANCE.md` without breaking existing artifact distribution.

## Audience

Platform engineers, security engineers, and release engineers responsible for the OCI registry and the verification boundary in Kubernetes admission or CI evaluation.

## Pre-conditions

- A supported Kubernetes release under `KUBERNETES_VERSION_GOVERNANCE.md` (for the verifier sidecar) or a CI runner pool with network access to the OCI registry.
- An OCI 1.1+ registry (Zot, Harbor 2.5+, GHCR, ECR) that supports the referrers API.
- A trust-store plan: local certificate store for development, remote trust store for production.
- A trust-policy file reviewed and approved by the security team.

## Procedure

### Step 1 — Bootstrap the trust store and trust policy

- Create a trust store with the root certificates that the verifier will trust; document the certificate chain and the rotation schedule.
- Author a trust policy that explicitly declares `trustedIdentities`, `expiry`, and `authenticTimestamp`; reject any policy that falls back to "skip".
- Pin the trust policy schema version to the Notary v2 verifier minor in `NOTARY_V2_VERSION_GOVERNANCE.md`.
- Apply the trust policy to the verifier (e.g., the `ratify` sidecar on Kubernetes, or the standalone CLI in CI).

### Step 2 — Sign provenance and SBOM artifacts

- Run `notation sign` against each artifact (image, SBOM, provenance statement) using a certificate that the trust store recognizes.
- For SLSA provenance, bind the attestation to the artifact digest using the `referrers` tag API; verify the binding locally before publishing.
- Confirm the signature payload includes the expected identity (`x509.subject`, `x509.san.uri`, or `x509.san.email`) and that the OIDC issuer is recognized.

### Step 3 — Sign at the artifact-construction step

- Sign the artifact at the same step that produces it (CI), not later; retroactive signing breaks the trust policy's "signed-at-issue" assumption.
- The signing identity MUST be the CI runner's federated identity, not a shared service-account key.
- Tag the signed artifact with the same digest as the original; do not duplicate artifacts.

### Step 4 — Stage verification in CI (audit)

- Run `notation verify` against every signed artifact in a CI gate; capture verification outcome.
- Triage every non-"verified" outcome: expired certificate, unknown identity, missing `authenticTimestamp`, or `referrers`-binding mismatch.
- Document the failure modes and the remediation steps in the runbook.

### Step 5 — Promote to admission enforcement

- Deploy the verifier (e.g., `ratify`) as a sidecar to the admission controller; configure the trust policy to require verification for the artifact types in scope.
- Confirm the admission webhook rejects artifacts that fail verification and that the rejection text includes the remediation.
- Validate the audit log entry under `NIST_SP_800_92_LOG_MANAGEMENT_GOVERNANCE.md`.

### Step 6 — Establish artifact and provenance retention

- Define a retention policy for signed SBOMs and provenance statements; the retention period MUST cover the artifact's deployment lifetime and at least one major-version cycle after retirement.
- Verify that the OCI registry's referrer index is retained for the same period.
- Cross-reference the retention policy with `ISO_IEC_18974_2024_OSPO_LICENSE_COMPLIANCE_GOVERNANCE.md` for open-source chain-of-custody requirements.

### Step 7 — Operational handoff

- Document the trust-store rotation procedure, the trust-policy update procedure, and the verifier-upgrade procedure.
- Schedule the next policy review at the cadence defined in `NOTARY_V2_VERSION_GOVERNANCE.md` (≤ 180 days).
- Hand off to the on-call rotation with the runbook, the trust-store access path, and the verifier-upgrade command.

## Rollback

- Set the trust policy to "skip" for the affected artifact type; the verifier falls back to permissive evaluation. This is a temporary state and MUST be ticket-tracked.
- If the verifier rejects artifacts that CI signed successfully, downgrade the verifier to the minor that matches the CI signer; do not re-sign artifacts with a newer signer without coordinating the verifier upgrade.
- If the trust store is corrupted, restore from the most recent verified backup; re-issue certificates and re-sign artifacts as required.

## References

- `NOTARY_V2_VERSION_GOVERNANCE.md`
- `COSIGN_VERSION_GOVERNANCE.md` — for image-signature co-deployment
- `KUBERNETES_VERSION_GOVERNANCE.md`
- `NIST_SP_800_53_R5_SCRM_OVERLAY_GOVERNANCE.md` — for SR-4 provenance
- `NIST_SP_800_92_LOG_MANAGEMENT_GOVERNANCE.md` — for audit retention
- `ISO_IEC_18974_2024_OSPO_LICENSE_COMPLIANCE_GOVERNANCE.md` — for chain-of-custody retention
- https://slsa.dev/ — for provenance predicate types
