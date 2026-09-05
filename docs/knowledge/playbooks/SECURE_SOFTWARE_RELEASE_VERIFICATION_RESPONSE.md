---
title: "Secure Software Release Verification Playbook"
owner: "Application Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Secure Software Release Verification Playbook

## Trigger

Use this playbook when a software release candidate is being prepared for production deployment, and a documented set of security, integrity, and compliance verifications must be satisfied before promotion.

## Scope

Apply the process to all release artifacts: source builds, container images, serverless packages, firmware, mobile binaries, configuration bundles, infrastructure-as-code modules, and the supporting metadata (SBOM, provenance, signature).

## Inputs

- release manifest with version, components, and source commits;
- build pipeline logs, attestations, and signing identities;
- vulnerability, secret, malware, and license scan results;
- threat model and security requirements traceability;
- change ticket, approver list, and deployment plan.

## Steps

1. **Confirm provenance.** Verify the build is reproducible from the recorded source commits and that SLSA or equivalent provenance attestation is present and valid.
2. **Review the SBOM.** Inspect the SBOM for completeness, format correctness (SPDX or CycloneDX), and unexpected components; compare against the expected dependency set.
3. **Run vulnerability scans.** Use SBOM-aware scanners to identify known vulnerabilities; confirm critical and high findings are remediated, accepted with documented justification, or blocked.
4. **Scan for secrets and malware.** Run secret scanners against the artifact and configuration; run malware and EICAR test pattern detection; reject on findings above the threshold.
5. **Verify license compliance.** Confirm the license inventory aligns with the project license policy; flag copyleft or restrictive licenses for legal review.
6. **Validate signatures and attestations.** Verify code signing, image signing (Cosign, GPG, PKCS#7), and in-toto attestations; reject releases with missing or invalid signatures.
7. **Confirm test coverage and security test results.** Validate that SAST, DAST, IAST, and dependency testing gates have passed; record the security test report identifier.
8. **Review configuration and secrets handling.** Confirm secrets are externalized, no default credentials remain, and configuration is appropriate for the target environment.
9. **Approve change ticket.** Capture approvals from engineering, security, and operations per the change management policy; record approver identity and timestamp.
10. **Promote and deploy.** Deploy through the documented pipeline; record the deployed artifact identifier and the audit log; archive verification evidence.

## Escalation

Escalate to the Application Security Lead, Engineering Owner, and Change Manager when:
- critical or exploitable vulnerabilities are unresolved;
- signatures, SBOM, or provenance attestations are missing or invalid;
- license or legal findings require counsel review;
- an exception is requested for any verification gate.

## Evidence

- signed artifact identifiers and signature verification record;
- SBOM, provenance, and attestation artifacts;
- scan reports with severity and remediation status;
- approval records and change ticket reference;
- deployment audit log entry.

## Completion Criteria

The release verification is considered complete when:
- all mandatory gates have passed or have documented exceptions;
- the artifact is signed and traceable to the source;
- approvals are captured in the change record;
- the artifact is deployed and the audit log is updated.

## Exceptions

Document any waiver of a mandatory gate with the technical justification, business rationale, approver, expiration, compensating control, and review schedule.

## Related Documents

- [SLSA Build Level 3 Governance](../reference/SLSA_BUILD_LEVEL_3_GOVERNANCE.md)
- [NIST SSDF SP 800-218](../reference/NIST_SSDF_SP_800_218.md)
- [OWASP Top 10 Verification Review](OWASP_TOP_10_VERIFICATION_REVIEW.md)
- [Secure Software Release Verification](SECURE_SOFTWARE_RELEASE_VERIFICATION.md)
- [Change Control](CHANGE_CONTROL.md)
