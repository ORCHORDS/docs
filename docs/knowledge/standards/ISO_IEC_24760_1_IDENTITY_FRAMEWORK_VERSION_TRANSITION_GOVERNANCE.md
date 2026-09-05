---
title: "ISO/IEC 24760-1:2022 Identity and Authentication — Framework Version Transition Governance"
standard: "ISO/IEC 24760-1:2022"
publisher: "International Organization for Standardization (ISO) and International Electrotechnical Commission (IEC)"
category: "standards"
subcategory: "identity-management"
canonical_url: "https://www.iso.org/standard/79453.html"
status: "approved"
classification: "public"
audience: "IAM architects, identity governance leads, identity assurance auditors"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# ISO/IEC 24760-1:2022 Identity Framework Version Transition Governance

## Profile

ISO/IEC 24760-1:2022 is the foundational part of the ISO/IEC 24760 series, providing a framework for identity management. It defines identity-related terms (identity, identifier, identity information, identity assurance level), introduces a reference model for identity management systems, and describes identity life-cycle management (provisioning, lifecycle, dissolution). This 2nd edition updates the 2011 edition to reflect modern identity practice, including federated identity, decentralized identity primitives, and digital-wallet use cases.

The 24760 series forms the conceptual basis for several ISO identity-related standards (ISO/IEC 29003 for identity proofing; ISO/IEC 29115 for assurance levels; ISO/IEC 29100 family for privacy in identity).

## Identifier

| Field | Value |
| --- | --- |
| Standard | ISO/IEC 24760-1:2022 (2nd edition) |
| Title | Information technology — Security techniques — A framework for identity management — Part 1: Terminology and concepts |
| Family | ISO/IEC 24760 (5 parts) |
| Companion | ISO/IEC 29003 (identity proofing), ISO/IEC 29115 (entity authentication assurance), ISO/IEC 29100 (privacy framework) |
| Cross-reference | NIST SP 800-63 (digital identity guidelines), NIST SP 800-63A through 63C |

## Identity Reference Model

| Component | Intent |
| --- | --- |
| Identity information | Attributes that identify an entity. |
| Identity information holder | Party who holds the identity information. |
| Identity information verifier | Party who consumes identity information for verification. |
| Identity management system | System that issues, manages, and revokes identity information. |
| Identity assertions | Statements about an identity (claims), including signed assertions. |

## Identity Lifecycle

| Stage | Activity |
| --- | --- |
| Enrolment | Establish identity, collect and verify initial identity information. |
| Provisioning | Issue credentials, register in target systems. |
| Maintenance | Update identity information; revoke, reissue, refresh credentials. |
| Dissolution | Retire the identity; revoke all credentials and references. |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Cite as the terminology and conceptual framework for identity management governance. |
| Identifier design | Use stable, non-sequential, non-recyclable identifiers for human and machine identities. |
| Assurance level | Select identity assurance levels per NIST SP 800-63 / ISO/IEC 29115; record in the identity record. |
| Lifecycle | Enforce enrolment, provisioning, maintenance, and dissolution controls in identity governance. |
| Federation | Document federation partners, trust frameworks, and correspondence mappings. |
| Privacy | Pair identity management with privacy controls per ISO/IEC 29100 and applicable privacy laws. |
| Audit | Audit identity records for staleness, duplicate identities, and orphaned credentials. |

## Implementation Notes

- The 2022 edition supersedes 24760-1:2011; transition plans are encouraged.
- Pair with NIST SP 800-63 for U.S. alignment and with ISO/IEC 29115 for assurance levels.
- Federated identity requires explicit trust framework documentation; align with Kantara Initiative, eIDAS, or applicable regional frameworks.
- Decentralized and self-sovereign identity (SSI) use identity-related concepts; map carefully and treat verifiability with cross-framework care.

## Companion Documents

- [ISO/IEC 29003 Identity Proofing](ISO_IEC_29003_IDENTITY_PROOFING_GOVERNANCE.md)
- [ISO/IEC 29115 Entity Authentication Assurance](ISO_IEC_29115_ENTITY_AUTH_ASSURANCE_GOVERNANCE.md)
- [NIST SP 800-63 Digital Identity Guidelines](NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
- [OAuth 2.1 Client Integration Response](../playbooks/OAUTH_2_1_CLIENT_INTEGRATION_RESPONSE.md)
