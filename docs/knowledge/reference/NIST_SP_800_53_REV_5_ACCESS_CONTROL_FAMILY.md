---
title: "NIST SP 800-53 Rev. 5 Access Control Family"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-53 Rev. 5 (September 2020, includes Rev. 5.1.1); https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final"
---

# NIST SP 800-53 Rev. 5 Access Control Family

## Scope

Reference card for the Access Control Family (AC) of NIST Special Publication 800-53 Revision 5, *Security and Privacy Controls for Information Systems and Organizations* (September 2020, with Rev. 5.1.1 updates). The publication is the canonical US federal control catalogue and a recognized baseline for private-sector profiles. The AC family defines the controls that govern access enforcement, account management, separation of duties, least privilege, and remote access.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-53 Rev. 5 (includes Rev. 5.1.1) |
| Family | AC — Access Control |
| Selected controls | AC-1 (policy and procedures), AC-2 (account management), AC-3 (access enforcement), AC-5 (separation of duties), AC-6 (least privilege), AC-17 (remote access), AC-20 (use of external systems) |
| Companion artifacts | SP 800-53A (assessment procedures), SP 800-53B (control baselines), NIST CSF, ISO/IEC 27001:2022 Annex A |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final |

## Plan

1. Reference SP 800-53 Rev. 5 AC family whenever a profile governs access control.
2. Adopt the AC-1 policy and procedures; document the access-control policy and the supporting procedures.
3. Apply AC-2 account management: account types, lifecycle, group membership, service accounts, and the review cadence.
4. Apply AC-3 access enforcement: enforcement mechanism (DAC, MAC, RBAC, ABAC), policy decision point, policy enforcement point.
5. Apply AC-5 separation of duties and AC-6 least privilege: identify conflicting duties, apply least-privilege roles, and document compensating controls where SoD is not feasible.
6. Apply AC-17 remote access: VPN, zero-trust network access, mTLS, and the remote-access review cadence.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- SP 800-53 Rev. 5 AC family controls.
- Internal access-control policy, account inventory, and access reviews.
- Identity provider (IdP) configuration, role definitions, and authorization rules.
- Remote-access infrastructure and audit records.

## ORCHORDS Profile

ORCHORDS treats the SP 800-53 Rev. 5 AC family as the canonical US federal reference for access control. Profiles that reference access control should cite SP 800-53 Rev. 5 by version, identify the AC controls in scope, and bind to NIST SP 800-207 (zero trust), ISO/IEC 27001:2022 Annex A 5.15–5.18, and the current identity standards (ISO/IEC 29115, NIST SP 800-63).

A profile that references "access control" without binding to a recognized framework is non-conformant.

## Implementation Notes

- Account management reviews should be periodic (typically quarterly for privileged accounts, semi-annually for general accounts).
- Service-account management is often weaker than user-account management; apply AC-2 controls to service accounts with the same rigor.
- Separation of duties conflicts should be identified from a documented role matrix; ad-hoc SoD analysis is non-conformant.
- Least privilege should be expressed at the role level and at the permission level; the role-to-permission mapping should be auditable.
- Remote-access infrastructure should be logged and monitored; the audit trail supports AC-17 review.

## Companion Documents

- [NIST SP 800-63 Digital Identity Guidelines Governance](../standards/NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
- [ISO/IEC 24760-1 Identity Framework Version Transition Governance](../standards/ISO_IEC_24760_1_IDENTITY_FRAMEWORK_VERSION_TRANSITION_GOVERNANCE.md)
- [ISO/IEC 27001:2022 ISMS Version Transition Governance](../standards/ISO_IEC_27001_2022_ISMS_VERSION_TRANSITION_GOVERNANCE.md)
- [Zero Trust Access Implementation Response](../playbooks/ZERO_TRUST_ACCESS_RESPONSE.md)
