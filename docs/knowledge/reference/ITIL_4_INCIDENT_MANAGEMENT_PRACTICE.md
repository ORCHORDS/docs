---
title: "ITIL 4 Incident Management Practice Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "ITIL 4 Foundation — IT Infrastructure Library; Axelos PeopleCert ITIL 4 publication"
---

# ITIL 4 Incident Management Practice Reference Card

## Scope

Reference card for the ITIL 4 Incident Management practice, the process of restoring service to normal operation as quickly as possible after a disruption, while minimizing impact on business operations. ITIL 4 Incident Management includes incident logging, categorization, prioritization, escalation, resolution, and closure. Profiles that govern IT service management should cite ITIL 4 Incident Management and bind to NIST SP 800-61 Incident Handling Governance, Google SRE Incident Management, and the Blameless Post-Incident Review.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | ITIL 4 Foundation (Axelos/PeopleCert) |
| Companion artifacts | NIST SP 800-61, Google SRE Incident Management, Blameless PIR |
| Source URL | https://www.axelos.com/certifications/itil-service-management/itil-4-foundation |

## Plan

1. Reference ITIL 4 Incident Management in service-management policy and incident response runbooks.
2. Define the incident lifecycle: log, categorize, prioritize, escalate (when needed), resolve, close.
3. Define the priority scheme (typically P1–P5) with explicit impact and urgency criteria.
4. Define the escalation matrix: functional escalation (to specialist teams) and hierarchical escalation (to management).
5. Adopt a single incident-tracking system with auditable state transitions.
6. Define the major-incident process for incidents that exceed a defined priority or duration threshold.
7. Define the service-request distinction; requests for new service or change are not incidents.
8. Bind to NIST SP 800-61 Incident Handling Governance for the alignment with NIST incident-handling process.
9. Bind to Google SRE Incident Management for the software-engineering incident-response alignment.
10. Hold blameless post-incident reviews for major incidents.
11. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- ITIL 4 Incident Management guidance.
- Incident-tracking system configuration.
- Escalation matrix and on-call schedule.
- Major-incident process documentation.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats ITIL 4 Incident Management as the canonical reference for the IT-service-management incident-management practice. Profiles that govern IT service management should adopt the incident lifecycle, priority scheme, escalation matrix, and major-incident process, and bind to NIST SP 800-61, Google SRE Incident Management, and the Blameless PIR.

A profile that governs IT service management without binding to ITIL 4 Incident Management is non-conformant.

## Implementation Notes

- ITIL 4 emphasizes the distinction between incidents (disruptions) and service requests (requests for new or changed service); this distinction drives prioritization.
- First-line support typically handles the majority of incidents; second-line and third-line support handle the rest.
- Major-incident management typically includes a separate manager and a dedicated communications cadence.
- The incident-tracking system should provide auditable state transitions and SLA tracking.
- Problem management (root-cause analysis across incidents) is a separate ITIL practice; incident management records provide inputs to problem management.

## Companion Documents

- [Google SRE Incident Management](GOOGLE_SRE_INCIDENT_MANAGEMENT.md)
- [NIST SP 800-61 Incident Handling Governance](../standards/NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md)
- [Blameless Post-Incident Review](BLAMELESS_POST_INCIDENT_REVIEW.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
