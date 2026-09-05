---
title: "NIST SP 800-63 Digital Identity Guidelines Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-63-3 (June 2017, errata 2020); https://pages.nist.gov/800-63-3/"
---

# NIST SP 800-63 Digital Identity Guidelines Governance

## Purpose

NIST Special Publication 800-63-3, *Digital Identity Guidelines* (June 2017, with errata 2020 and subsequent supplemental publications), is the foundational reference for digital identity in the US federal government and is widely adopted by industry. The publication defines Identity Assurance Levels (IAL), Authenticator Assurance Levels (AAL), and Federation Assurance Levels (FAL). Profiles that govern digital identity should reference SP 800-63-3 by version and bind it to ISO/IEC 29115, ISO/IEC 24760, ISO/IEC 29003, and the regulator-specific KYC requirements.

## Current context and source status

SP 800-63-3 is the current published edition; SP 800-63-4 is in active draft. Profiles should reference SP 800-63-3 by version, include the errata update, and identify the SP 800-63-4 draft state. NIST SP 800-63-A (IAL), SP 800-63-B (AAL), and SP 800-63-C (FAL) are the current companion publications.

## Governance workflow and controls

1. Plan: identify the digital identity use case, the IAL/AAL/FAL required, the legal and regulatory framework, and the relationship to the broader identity-management system.
2. Identity proofing: implement the IAL-required identity-proofing process per SP 800-63-A, with the authoritative-source validation, evidence handling, and re-proofing rules.
3. Authentication: implement the AAL-required authentication process per SP 800-63-B, with the authenticator type, the credential lifecycle, and the session-management rules.
4. Federation: implement the FAL-required federation process per SP 800-63-C, with the assertion format, the assertion signer, the trust anchors, and the privacy-preserving pseudonymous identifier guidance.
5. Reauthentication: implement the reauthentication rules per the AAL, including the session-timeout and inactivity-timeout rules.
6. Risk-based escalation: implement the risk-based escalation rules per SP 800-63-B, including the step-up authentication triggers.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Validation and evidence

- Digital identity policy aligned with SP 800-63-3, the IAL/AAL/FAL mapping, and the applicable regulator-specific requirements.
- Identity-proofing, authentication, and federation records for representative transactions.
- Federation trust framework (for example OpenID Connect, SAML, FIDO) with the assertion signer and trust anchors.
- Session management rules, including the reauthentication rules and the inactivity-timeout rules.
- Periodic competency assessment for identity and authentication operators.

Evidence that omits the IAL/AAL/FAL mapping, the federation trust framework, or the session-management rules does not establish SP 800-63-3 conformance.

## Failure correction

Common defects include missing IAL/AAL/FAL mapping, ad-hoc federation trust, and inadequate session-management rules. Corrective actions include the explicit mapping, vetted federation profile, and tested session-management rules at the integration layer.

## Companion documents

- [ISO/IEC 24760-1 Identity Framework Version Transition Governance](ISO_IEC_24760_1_IDENTITY_FRAMEWORK_VERSION_TRANSITION_GOVERNANCE.md)
- [ISO/IEC 29003 Identity Proofing Governance](ISO_IEC_29003_IDENTITY_PROOFING_GOVERNANCE.md)
- [ISO/IEC 29115 Entity Authentication Assurance Governance](ISO_IEC_29115_ENTITY_AUTH_ASSURANCE_GOVERNANCE.md)
- [NIST SP 800-63-3 Digital Identity Governance](NIST_SP_800_63_3_DIGITAL_IDENTITY_GOVERNANCE.md)
- IETF OAuth 2.1 Authorization Framework
- OpenID Connect Core 1.0
- [OAuth 2.1 Client Integration Response](../playbooks/OAUTH_2_1_CLIENT_INTEGRATION_RESPONSE.md)
