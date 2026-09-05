---
title: "ISO/IEC 27035-2:2023 Incident Response Guidelines Version Transition Governance"
standard: "ISO/IEC 27035-2:2023"
publisher: "International Organization for Standardization (ISO) and International Electrotechnical Commission (IEC)"
category: "standards"
subcategory: "incident-management"
canonical_url: "https://www.iso.org/standard/78973.html"
status: "approved"
classification: "public"
audience: "Incident response leads, security operations, governance and audit"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# ISO/IEC 27035-2:2023 Incident Response Guidelines Version Transition Governance

## Profile

ISO/IEC 27035-2:2023 provides guidelines for incident response planning and operations, complementing the principles defined in ISO/IEC 27035-1 (incident management overview). It is part of the ISO/IEC 27035 family, which together describe the planning, detection, reporting, assessment, response, and lessons-learned phases of security incident management.

The 2023 edition updates ISO/IEC 27035-2:2016 to align with evolving threats (ransomware, supply chain compromise, AI-assisted attacks) and to integrate lessons from the prior version. It pairs with ISO/IEC 27035-3 (incident response exercises) and the ISO/IEC 27000-series control family.

## Identifier

| Field | Value |
| --- | --- |
| Standard | ISO/IEC 27035-2:2023 (2nd edition) |
| Title | Information technology — Information security incident management — Part 2: Guidelines for incident response planning and operations |
| Companion | ISO/IEC 27035-1:2023 (overview); ISO/IEC 27035-3:2020 (exercises); ISO/IEC 27001 A.5.24–A.5.28 (incident management controls) |

## Lifecycle Phases

| Phase | Activity |
| --- | --- |
| Plan and prepare | Define incident response policy, roles, escalation paths, communication channels, tools, and detection capabilities. |
| Detect and report | Capture, triage, and route events from detection sources to responders with sufficient context. |
| Assess and decide | Confirm scope, severity, impact, and required escalation; record initial findings and hypothesis. |
| Respond | Contain, eradicate, recover, and communicate through authorized channels; coordinate with stakeholders. |
| Learn | Conduct post-incident review; track corrective actions; update playbooks, training, and controls. |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Cite as the incident-response methodology basis for ORCHORDS incident response governance. |
| Phase model | Use the five-phase model across all incident categories (security, privacy, AI). |
| Plan documentation | Maintain an incident response plan and per-scenario playbooks; review at planned intervals. |
| Detection source coverage | Map detection sources (SIEM, EDR, NDR, user reports, third-party advisories) to coverage requirements. |
| Reporting | Use the standard's incident classification scheme to align internal reporting and external notifications (regulators, customers, sector ISACs). |
| Exercises | Pair with ISO/IEC 27035-3 for exercises at planned cadence; rotate across scenarios. |
| Post-incident review | Conduct PIR per the standard's learning phase; track corrective actions. |

## Implementation Notes

- The 2023 edition supersedes ISO/IEC 27035-2:2016; transition plans are encouraged.
- Pair with NIST SP 800-61 (incident handling) for U.S. federal systems and with the NIST CSF for cross-framework reporting.
- Privacy incident handling pairs with ISO/IEC 29134 (privacy impact assessment) and GDPR Art. 33 (where applicable).
- AI incident handling requires AI RMF 1.0 (NIST AI 100-1) and EU AI Act Article 73 reporting obligations.

## Companion Documents

- [ISO/IEC 27035-1:2023 Incident Management Overview](ISO_IEC_27035_1_INCIDENT_MANAGEMENT_GOVERNANCE.md)
- [ISO/IEC 27035-3:2020 Incident Response Exercises](ISO_IEC_27035_3_INCIDENT_RESPONSE_EXERCISES_GOVERNANCE.md)
- [NIST SP 800-61 Incident Handling](NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md)
- [ISO/IEC 27001:2022 Information Security Management](ISO_IEC_27001_2022_ISMS_VERSION_TRANSITION_GOVERNANCE.md)
- [Cybersecurity Incident Response Playbook](../playbooks/CYBERSECURITY_INCIDENT_RESPONSE.md)
