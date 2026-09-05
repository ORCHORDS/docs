---
title: "Google SRE Incident Management Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Google SRE Book Chapters 12–14 (Incident Management, Postmortem, Postmortem Culture); https://sre.google/sre-book/managing-incidents/"
---

# Google SRE Incident Management Reference Card

## Scope

Reference card for Google SRE incident-management practices: the incident command structure (Incident Commander, Communications Lead, Operations Lead, Planning Lead, Scribe), the incident-response lifecycle (detect, triage, mitigate, resolve, learn), and the tooling expectations (incident channel, incident tracker, status page, paging system). Profiles that govern on-call or incident response should adopt the SRE incident-management structure and bind to the ITIL 4 Incident Management Practice, NIST SP 800-61 Incident Handling Governance, and the Blameless Post-Incident Review.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | Google SRE Book Chapters 12, 13, and 14 |
| Companion artifacts | ITIL 4 Incident Management, NIST SP 800-61, Blameless PIR, SLO Definition, Error Budget Policy |
| Source URL | https://sre.google/sre-book/managing-incidents/ |

## Plan

1. Reference Google SRE incident management in incident response runbooks and on-call documentation.
2. Adopt the incident command structure: Incident Commander, Communications Lead, Operations Lead, Planning Lead, Scribe.
3. Adopt the incident severity scale (typically sev-1 through sev-4) with explicit definitions.
4. Establish incident channels (chat), an incident tracker (issue or ticket), a status page, and a paging system.
5. Define handoff procedures when the incident spans time zones or teams.
6. Adopt the postmortem culture; hold a blameless post-incident review for every sev-1 and sev-2 incident.
7. Bind to ITIL 4 Incident Management Practice for the broader incident-management framework.
8. Bind to NIST SP 800-61 Incident Handling Governance for the alignment with NIST incident-handling process.
9. Bind to SLO Definition and Error Budget Policy for the reliability-impact analysis.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- Google SRE Book (Chapters 12–14).
- On-call rotation schedule and escalation policy.
- Incident response tooling: paging system, chat platform, status page, incident tracker.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats Google SRE incident management as the canonical reference for incident response in a software-engineering organization. Profiles that govern on-call or incident response should adopt the incident command structure, severity scale, and tooling expectations, hold blameless post-incident reviews, and bind to ITIL 4 Incident Management Practice, NIST SP 800-61, and the SLO/Error Budget policy.

A profile that governs on-call without binding to Google SRE incident management is non-conformant.

## Implementation Notes

- The Incident Commander (IC) is responsible for coordination, not technical resolution; the IC delegates technical work to the Operations Lead or subject-matter experts.
- The Scribe role records the timeline; this frees the IC and Operations Lead from note-taking.
- Communications are typically to internal stakeholders during the incident and to external customers via the status page.
- Severity definitions should include customer-impact criteria (for example, percentage of customers affected, revenue impact) and not just internal-impact criteria.
- Handoff should include a written summary and an explicit acknowledgment from the incoming IC.

## Companion Documents

- [Google SRE Release Engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md)
- [Blameless Post-Incident Review](BLAMELESS_POST_INCIDENT_REVIEW.md)
- [SLO Definition](SERVICE_LEVEL_OBJECTIVE_DEFINITION.md)
- [Error Budget Policy](ERROR_BUDGET_POLICY.md)
- [ITIL 4 Incident Management Practice](ITIL_4_INCIDENT_MANAGEMENT_PRACTICE.md)
- [NIST SP 800-61 Incident Handling Governance](../standards/NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md)
