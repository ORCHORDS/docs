---
title: "ISO/IEC 29115 Entity Authentication Assurance Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "ISO/IEC 29115:2013; https://www.iso.org/standard/45138.html"
---

# ISO/IEC 29115 Entity Authentication Assurance Governance

## Purpose

ISO/IEC 29115:2013, *Information technology — Security techniques — Entity authentication assurance framework*, defines four Levels of Assurance (LoA1–LoA4) for entity authentication. The framework maps authentication technologies, processes, and controls to assurance levels and provides a common vocabulary for cross-organizational trust. Profiles that govern authentication assurance should reference ISO/IEC 29115 and bind it to NIST SP 800-63-A (Authenticator Assurance Levels), ISO/IEC 24760-1, ISO/IEC 29003, and the FIDO Alliance / OpenID Connect specifications.

## Current context and source status

ISO/IEC 29115:2013 was published in April 2013 and remains the current edition as of September 2026. Profiles should call out the 2013 publication date and identify the companion standards. NIST SP 800-63-3 defines Authenticator Assurance Levels (AAL1–AAL3) that map roughly to ISO/IEC 29115 LoA1–LoA3; the crosswalk should be documented in the profile.

## Governance workflow and controls

1. Plan: identify the authentication use case, the assurance level required, the legal and regulatory framework, and the relationship to the broader identity-management system.
2. Authentication: implement the authentication mechanism at the required assurance level, including the authenticator type, the credentials, and the binding to the entity.
3. Validation: validate the authentication transaction with the supporting evidence retained for audit.
4. Mapping: maintain the crosswalk between ISO/IEC 29115 LoA and the organization's internal assurance-level definitions, including the mapping to NIST SP 800-63-A AALs.
5. Federation: when authentication is federated, document the trust framework, the assertion format, the assertion signer, and the trust anchors.
6. Lifecycle: define the rules for credential re-issuance, suspension, revocation, and termination, with the events logged.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Validation and evidence

- Authentication-assurance policy aligned with ISO/IEC 29115, NIST SP 800-63-A, and the applicable regulator-specific requirements.
- LoA / AAL mapping table with the controls at each level.
- Authentication-event records with the assertion type, the assertion signer, and the trust anchor.
- Federation trust framework (for example OpenID Connect, SAML, FIDO).
- Periodic competency assessment for authentication operators.

Evidence that omits the LoA / AAL mapping, the federation trust framework, or the lifecycle-event records does not establish ISO/IEC 29115 conformance.

## Failure correction

Common defects include missing LoA / AAL mapping, ad-hoc federation trust, and unintegrated revocation. Corrective actions include the explicit mapping, vetted federation profile, and integrated revocation that is tested at the integration layer.

## Companion documents

- [ISO/IEC 24760-1 Identity Framework Version Transition Governance](ISO_IEC_24760_1_IDENTITY_FRAMEWORK_VERSION_TRANSITION_GOVERNANCE.md)
- [ISO/IEC 29003 Identity Proofing Governance](ISO_IEC_29003_IDENTITY_PROOFING_GOVERNANCE.md)
- [NIST SP 800-63 Digital Identity Guidelines Governance](NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
- IETF OAuth 2.1 Authorization Framework
- OpenID Connect Core 1.0
- FAPI 2.0 Security Profile
- [OAuth 2.1 Client Integration Response](../playbooks/OAUTH_2_1_CLIENT_INTEGRATION_RESPONSE.md)
