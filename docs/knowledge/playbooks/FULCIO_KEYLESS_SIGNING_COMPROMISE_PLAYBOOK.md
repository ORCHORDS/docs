# Fulcio Keyless Signing Compromise Response Playbook

## Purpose

Respond to a Fulcio trust-root compromise, OIDC issuer misconfiguration, or keyless-signing pipeline incident under the version, issuer-allow-list, and trust-root constraints in `FULCIO_VERSION_GOVERNANCE.md`, so that keyless signatures remain verifiable and that the impact window is documented for downstream consumers.

## Audience

Supply-chain security engineers, platform engineers, incident responders, and compliance leads responsible for Sigstore keyless-signing operations.

## Pre-conditions

- Fulcio version and OIDC issuer allow-list are documented per environment under `FULCIO_VERSION_GOVERNANCE.md`.
- Rekor inclusion proof retention is documented and monitored under `REKOR_VERSION_GOVERNANCE.md`.
- An incident-response plan exists; Fulcio-specific roles (issuer owner, verifier owner, attestation owner) are documented.

## Procedure

### Step 1 — Detect and confirm the compromise

- Confirm the trigger: trust-root rotation event, OIDC issuer misconfiguration, or unusual issuance volume.
- Capture evidence: Fulcio version, OIDC issuer URL, certificate serial number range, and the suspected issuance window.
- Open an incident in the tracker; assign the Fulcio issuer owner as incident commander.

### Step 2 — Pause keyless signing

- Halt all CI jobs that use `cosign sign --fulcio-url` or `gitsign` until the issuer is re-validated.
- Notify downstream consumers that signatures issued during the suspected window are flagged as "pending verification".
- Document the pause window in the incident record.

### Step 3 — Validate the issuer and the trust root

- Re-fetch the sigstore-root TUF metadata; compare to the pinned version; document any delta.
- Validate the OIDC issuer allow-list against the workload identity configuration; remove unintended issuers.
- For OIDC issuer misconfiguration: revoke the misconfigured workload identity in the identity provider; rotate any long-lived secrets.
- For trust-root compromise: rotate to the documented fallback trust root; record the rotation in the sigstore-root TUF mirror.

### Step 4 — Re-issue or re-verify impacted artifacts

- For artifacts signed during the suspected window: re-sign with the validated Fulcio issuer; record the new certificate serial number and Rekor inclusion proof.
- For artifacts that cannot be re-signed (consumed and immutable): publish a verifier advisory; downstream verifiers must treat the original signature as revoked.
- Update the SBOM and the SSDF attestation to reflect the re-signed artifact set.

### Step 5 — Communicate and document

- Notify downstream consumers through the documented security-advisory channel; include the impacted signature window and the remediation action.
- File a CRA notification if the impact window includes EU market releases (Article 11(4) actively-exploited-vulnerability reporting).
- File an SSDF attestation delta under NIST SP 800-218 v1.1 if the impacted release is in a federal-procurement scope.
- Produce a post-incident review within 14 days; feed findings into the Fulcio governance card.

### Step 6 — Resume keyless signing

- Re-enable CI keyless signing only after the issuer and trust root are validated.
- Run a canary signature and verify the inclusion proof from a clean workstation.
- Document the resumption and close the incident.

## Rollback

- If the trust-root rotation produces unexpected verifier behaviour, roll back to the previous trust-root pin through the sigstore-root TUF mirror.
- If the OIDC issuer allow-list cannot be restored cleanly, disable keyless signing and fall back to long-lived Cosign keys; track the long-lived keys under the documented key-management governance.
- Do not delete incident evidence; retain for the documented retention period (default 7 years for federal-procurement-bound releases).

## References

- `FULCIO_VERSION_GOVERNANCE.md`
- `REKOR_VERSION_GOVERNANCE.md`
- `COSIGN_VERSION_GOVERNANCE.md`
- `NIST_SP_800_218_SSDF_V1_1_GOVERNANCE.md`
- `EU_CYBER_RESILIENCE_ACT_2024_GOVERNANCE.md`
- `SLSA_BUILD_LEVEL_3_GOVERNANCE.md`
