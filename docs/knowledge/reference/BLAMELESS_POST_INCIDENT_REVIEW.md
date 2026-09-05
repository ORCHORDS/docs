---
title: "Blameless Post-Incident Review Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Etsy Debriefing; Google SRE Book; Atlassian Incident Handbook; Jeli/Allie K. Miller blameless-postmortem practice"
---

# Blameless Post-Incident Review Reference Card

## Scope

Reference card for blameless post-incident review (PIR), the practice of analyzing incidents to identify systemic causes and improvement actions without assigning personal blame. Blameless PIR requires a just culture, a structured template, a facilitator who is not the incident commander, and an action-tracking mechanism. Profiles that govern incident management should adopt blameless PIR and bind to the SLO Definition, Error Budget Policy, ITIL 4 Incident Management Practice, and the SRE incident-management and release-engineering references.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | Etsy Debriefing, Google SRE Book Chapter 14 (Postmortem Culture), Atlassian Incident Handbook |
| Companion artifacts | Google SRE Incident Management, Google SRE Release Engineering, SLO Definition, Error Budget Policy, ITIL 4 Incident Management |
| Source URL | https://sre.google/sre-book/postmortem-culture/ |

## Plan

1. Reference blameless PIR in incident-management policy and on-call runbooks.
2. Hold a PIR for every severity-1 and severity-2 incident, and for severity-3 incidents that recur within a defined window.
3. Use a structured template: timeline, contributing factors (not causes), what went well, what went poorly, where we got lucky, action items.
4. Assign a facilitator who is not the incident commander and who is trained in blameless facilitation.
5. Frame findings in terms of systems, processes, and tools — not people.
6. Track action items to closure with owners and deadlines; review at a defined cadence.
7. Bind to SLO Definition and Error Budget Policy for the reliability-impact analysis.
8. Bind to ITIL 4 Incident Management Practice for the incident-management alignment.
9. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- Incident timeline and chat logs.
- Incident commander statement and responder statements.
- Action-tracking system (for example, Jira, GitHub Issues) with action items, owners, deadlines, and status.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats blameless PIR as the canonical practice for learning from incidents. Profiles that govern incident management should hold a PIR for every significant incident, use a structured template, use an independent facilitator trained in blameless facilitation, frame findings in terms of systems rather than people, track action items to closure, and bind to the SLO Definition, Error Budget Policy, and ITIL 4 Incident Management Practice.

A profile that holds post-incident reviews without a blameless framing is non-conformant.

## Implementation Notes

- Just culture distinguishes between normal mistakes, at-risk behavior, and reckless behavior; the PIR should treat normal mistakes as system-improvement opportunities.
- The facilitator should be trained in blameless facilitation; the role is distinct from the incident commander.
- Action items should be specific, time-bound, and owned; vague action items (for example, "improve monitoring") are non-conformant.
- Action items should be reviewed at a defined cadence (for example, weekly) until closure.
- Lessons learned should be shared beyond the immediate responders; aggregate trends across PIRs inform systemic improvements.

## Companion Documents

- [Google SRE Incident Management](GOOGLE_SRE_INCIDENT_MANAGEMENT.md)
- [Google SRE Release Engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md)
- [SLO Definition](SERVICE_LEVEL_OBJECTIVE_DEFINITION.md)
- [Error Budget Policy](ERROR_BUDGET_POLICY.md)
- [ITIL 4 Incident Management Practice](ITIL_4_INCIDENT_MANAGEMENT_PRACTICE.md)
- [NIST SP 800-61 Incident Handling Governance](../standards/NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md)
