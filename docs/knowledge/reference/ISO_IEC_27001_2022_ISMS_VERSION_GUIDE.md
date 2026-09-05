---
title: "ISO/IEC 27001:2022 ISMS Version Guide"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "ISO/IEC 27001:2022; https://www.iso.org/standard/27001"
---

# ISO/IEC 27001:2022 ISMS Version Guide

## Scope

Reference card for ISO/IEC 27001:2022, *Information security, cybersecurity and privacy protection — Information security management systems — Requirements*. Profiles that govern an ISMS should reference this card to identify the clauses (4–10) and the Annex A control structure (93 controls in four themes). The companion implementation guide is ISO/IEC 27002:2022; the companion implementation, measurement, and risk-management standards are ISO/IEC 27003, ISO/IEC 27004, and ISO/IEC 27005.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | ISO/IEC 27001:2022 |
| Status | Published (October 2022); current edition |
| Supersedes | ISO/IEC 27001:2013 |
| Companion | ISO/IEC 27002:2022 (controls), ISO/IEC 27003 (implementation), ISO/IEC 27004 (measurement), ISO/IEC 27005 (risk management), ISO 31000:2018 |
| Annex A themes | Organizational (37 controls), People (8), Physical (14), Technological (34) — 93 total |
| Source URL | https://www.iso.org/standard/27001 |

## Plan

1. Reference ISO/IEC 27001:2022 by version whenever a profile governs an ISMS.
2. Bind the ISMS scope to the organization's context and the Statement of Applicability.
3. Use ISO/IEC 27002:2022 as the implementation guide for the Annex A controls.
4. Apply ISO/IEC 27005 for the risk-management method; cross-reference ISO 31000:2018.
5. Track the transition from the 2013 Annex A control set (114 controls) to the 2022 Annex A control set (93 controls) with a documented mapping.
6. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- ISO/IEC 27001:2022 clauses 4–10 and Annex A control set.
- ISO/IEC 27002:2022 implementation guidance.
- ISO/IEC 27005 risk-management method.
- Internal ISMS scope, Statement of Applicability, risk-treatment plan, and management review records.

## ORCHORDS Profile

ORCHORDS treats ISO/IEC 27001:2022 as the canonical reference for an ISMS. Profiles that reference ISO/IEC 27001 should cite the version, identify the Annex A themes in use, and bind to ISO/IEC 27002:2022 for implementation guidance. The governance companion card is `ISO_IEC_27001_2022_ISMS_VERSION_TRANSITION_GOVERNANCE.md`; this card is the reference card.

Profiles that reference ISO/IEC 27001:2013 should be re-ratified against the 2022 edition rather than carried forward.

## Implementation Notes

- The 2022 control set introduces 11 new controls (for example 5.7 Threat intelligence, 5.23 Information security for use of cloud services, 5.30 ICT readiness for business continuity) and renames several existing controls.
- The Statement of Applicability (SoA) must list every Annex A control with its applicability, the implementation status, and the justification for inclusion or exclusion.
- The risk-management method should be documented at the ISMS level (ISO/IEC 27005) with the operational risk-management decisions documented at the asset or system level.
- Management review must include the status of previous actions, changes in internal and external issues, performance of the ISMS, and the opportunities for improvement.
- Continual improvement should be evidence-based, with corrective actions tracked to closure.

## Companion Documents

- [ISO/IEC 27001:2022 ISMS Version Transition Governance](../standards/ISO_IEC_27001_2022_ISMS_VERSION_TRANSITION_GOVERNANCE.md)
- [ISO 31000:2018 Risk Management Version Guide](ISO_31000_2018_RISK_MANAGEMENT_VERSION_GUIDE.md)
- [ISO/IEC 27033-1 Network Security Version Transition Governance](../standards/ISO_IEC_27033_1_NETWORK_SECURITY_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SP 800-12 Introduction to Information Security Governance](../standards/NIST_SP_800_12_INFO_SEC_INTRODUCTION_GOVERNANCE.md)
- [Cybersecurity Incident Response Playbook](../playbooks/CYBERSECURITY_INCIDENT_RESPONSE.md)
