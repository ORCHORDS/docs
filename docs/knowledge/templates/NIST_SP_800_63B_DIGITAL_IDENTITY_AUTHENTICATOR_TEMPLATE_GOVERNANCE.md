# NIST SP 800-63B Digital Identity Authenticator Template Governance

## Purpose
Establish the governance pattern for templating authenticator assurance levels (AALs) and authenticator lifecycle management per NIST SP 800-63B (Digital Identity Guidelines — Authentication and Lifecycle Management).

## Scope
Applies to every authenticator issued, managed, or relied upon by the studio for digital identity assurance, regardless of the type of authenticator (password, OTP, cryptographic, biometric).

## Workflow
1. Map each authenticator use case to the appropriate AAL (1, 2, or 3) per NIST SP 800-63B and document the rationale; AAL3 requires cryptographic hardware authenticators.
3. For each authenticator, maintain a lifecycle record covering issuance, enrollment verification, renewal, re-issuance, and revocation.
5. Apply minimum authenticator requirements per AAL: AAL1 requires either a memorized secret or a single-factor cryptographic device; AAL2 requires multi-factor authentication with approved cryptographic authenticators; AAL3 mandates hardware cryptographic authenticators with verifier impersonation resistance.
7. Document fallback authentication mechanisms (e.g., password reset, recovery codes) and apply rate limiting and additional verification per NIST SP 800-63B §5.1.1.2.
9. Maintain a verifier-side controls log: rate limiting, replay resistance, phishing resistance (where applicable), and authenticator binding (per AAL2/AAL3).

## Controls and evidence
- Authenticator inventory with type, AAL assignment, owner, and last-review date.
- Lifecycle event log for each authenticator covering issuance, renewal, revocation, and reset.
- Verifier controls log with rate-limiting rules, replay-resistance mechanisms, and authenticator binding details.
- Annual review of authenticator policies against the latest NIST SP 800-63B publication.

## Validation
- Re-validate the AAL mapping for a sample of 10 use cases and confirm consistency with the studio's risk assessment.
- Verify that AAL3 authenticator assignments use only hardware cryptographic devices.
- Confirm that all verifiers implement rate limiting, replay resistance, and authenticator binding per the assigned AAL.

## Failure correction
- **Authenticator use case under-mapped to AAL** → re-assess the risk, update the AAL, and reissue authenticators as needed.
- **Lifecycle event missing or out of order** → reconstruct the lifecycle record, document the gap, and tighten the lifecycle event logging.
- **Verifier controls drift** → suspend the verifier, document the drift, and remediate the missing control before reactivating.

## Limitations
- NIST SP 800-63B is one of three documents in the SP 800-63-4 series; consult SP 800-63A for identity proofing and SP 800-63C for federation.
- AAL3 hardware requirements may be impractical for some user populations; consider compensating controls (e.g., in-person identity proofing at re-issuance).
- Biometric authenticators raise privacy concerns; consult applicable privacy regulations (e.g., GDPR Art. 9) before deploying.

## Scope note
This article is part of the templates leaf. Cross-reference: NIST_SP_800_63A_IDENTITY_PROOFING_TEMPLATE_GOVERNANCE.md, NIST_SP_800_53_REV5_CONTROL_TEMPLATES_GOVERNANCE.md, ISO_27018_CLOUD_PII_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- NIST SP 800-63B — Digital Identity Guidelines — Authentication and Lifecycle Management: https://pages.nist.gov/800-63-3/sp800-63b.html
- NIST SP 800-63-4 — Digital Identity Guidelines (Revision 4 draft): https://pages.nist.gov/800-63-4/
- NIST SP 800-63A — Digital Identity Guidelines — Identity Proofing and Enrollment: https://pages.nist.gov/800-63-3/sp800-63a.html
- NIST SP 800-63C — Digital Identity Guidelines — Federation and Assertions: https://pages.nist.gov/800-63-3/sp800-63c.html
- FIPS 140-3 — Security Requirements for Cryptographic Modules: https://csrc.nist.gov/publications/detail/fips/140/3/final