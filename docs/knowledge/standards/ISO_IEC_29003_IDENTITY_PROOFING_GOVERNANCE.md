---
title: "ISO/IEC 29003 Identity Proofing Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "ISO/IEC 29003:2018; https://www.iso.org/standard/67481.html"
---

# ISO/IEC 29003 Identity Proofing Governance

## Purpose

ISO/IEC 29003:2018, *Information technology — Security techniques — Identity proofing*, defines requirements for the registration and identity-proofing of a natural person. The publication provides a foundation for identity assurance and is one of the supporting standards for NIST SP 800-63-A (Identity Assurance Level definitions). Profiles that govern identity proofing for customer onboarding, employee onboarding, or remote identity verification should reference ISO/IEC 29003 and bind it to NIST SP 800-63, ISO/IEC 29115, ISO/IEC 24760, and the regulator-specific KYC requirements.

## Current context and source status

ISO/IEC 29003:2018 was published in March 2018 and remains the current edition as of September 2026. Profiles should call out the 2018 publication date and identify the companion standards. NIST SP 800-63-3 (the current NIST identity assurance standard) and the SP 800-63-4 draft should be referenced as the assurance-level mapping.

## Governance workflow and controls

1. Plan: identify the identity-proofing use case, the assurance level required, the legal and regulatory framework, and the relationship to the broader identity-management system.
2. Enrol: register the applicant, collect identity evidence, capture biometrics if required, and bind the applicant to the identity record.
3. Identity evidence validation: validate the identity evidence against authoritative sources, perform forgery and tampering checks, and record the validation outcome.
4. Verification: verify the applicant against the validated identity evidence; for remote proofing, use an approved remote-proofing method.
5. Binding: bind the validated identity to a credential that is then issued through a credential-management process.
6. Lifecycle: define the rules for credential re-issuance, suspension, revocation, and termination.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Validation and evidence

- Identity-proofing policy aligned with ISO/IEC 29003, NIST SP 800-63-A, and the applicable KYC framework.
- Records of enrolment, evidence validation, and verification for representative applicants.
- Authoritative-source integration (for example government identity documents, KYC data providers) with documented data-handling rules.
- Lifecycle-event records (issuance, re-issuance, suspension, revocation).
- Periodic competency assessment for identity-proofing operators.

Evidence that omits the assurance-level mapping, the evidence-validation records, or the lifecycle-event records does not establish ISO/IEC 29003 conformance.

## Failure correction

Common defects include missing assurance-level mapping, ad-hoc remote-proofing procedures, and unintegrated authoritative-source validation. Corrective actions include an explicit assurance-level matrix, a vetted remote-proofing procedure, and authoritative-source integration tested at the integration layer.

## Companion documents

- [ISO/IEC 24760-1 Identity Framework Version Transition Governance](ISO_IEC_24760_1_IDENTITY_FRAMEWORK_VERSION_TRANSITION_GOVERNANCE.md)
- [ISO/IEC 29115 Entity Authentication Assurance Governance](ISO_IEC_29115_ENTITY_AUTH_ASSURANCE_GOVERNANCE.md)
- [NIST SP 800-63 Digital Identity Guidelines Governance](NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
- [NIST SP 800-63-3 Digital Identity Governance](NIST_SP_800_63_3_DIGITAL_IDENTITY_GOVERNANCE.md)
- [NIST SP 800-207 Zero Trust Architecture](../reference/NIST_SP_800_207_ZERO_TRUST_GOVERNANCE.md)
- [Zero Trust Access Implementation Response](../playbooks/ZERO_TRUST_ACCESS_RESPONSE.md)
