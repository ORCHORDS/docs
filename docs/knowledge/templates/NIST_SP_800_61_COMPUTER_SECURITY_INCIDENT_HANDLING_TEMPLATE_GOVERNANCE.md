---
title: "NIST SP 800-61 Computer Security Incident Handling Guide Template Governance"
standard: "NIST SP 800-61 Rev 3 (Computer Security Incident Handling Guide)"
publisher: "National Institute of Standards and Technology"
category: "governance-template"
subcategory: "incident-response"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/61/r3/final"
status: "approved"
classification: "public"
audience: "security operations, incident response, IT management"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-61 Rev 3 — Computer Security Incident Handling Guide Template Governance

## Profile

This template governs incident response handling under NIST SP 800-61 Rev 3's four-phase model: preparation; detection and analysis; containment, eradication, and recovery; and post-incident activity. It anchors incident handling in a learning-oriented programme rather than a reactive fire-fighting workflow.

## Identifier table

| Field | Value |
| --- | --- |
| Standard | NIST SP 800-61 Rev 3 |
| Title | Computer Security Incident Handling Guide |
| Publisher | NIST Computer Security Resource Center |
| Topic | Incident Response Lifecycle |
| Governance role | Incident response programme governance |

## Scope

The template applies to incidents that affect confidentiality, integrity, availability of information systems or data. It covers:

- Preparation activities, including staffing, tooling, runbook authoring, and tabletop exercises.
- Detection sources (SIEM, EDR, NDR, user reports, partner notifications, threat intelligence).
- Triage and categorisation using impact, urgency, and recoverability.
- Containment, eradication, and recovery actions with explicit evidence capture.
- Coordination across legal, privacy, communications, customer success, and engineering.
- Post-incident review and durable corrective actions.

## Plan / Inputs

- Incident response plan with on-call rotation and escalation paths.
- Contact roster including law enforcement, regulators, sector ISAC, and key vendors.
- Tooling baseline: forensic kit, secure communications, case management system, evidence vault.
- Communications templates for internal stakeholders, customers, and public statements.
- Authority matrix for containment decisions and emergency change approval.

## ORCHORDS Profile table

| ORCHORDS field | Guidance |
| --- | --- |
| Incident ID | Stable identifier that survives across tooling, tickets, and reports. |
| Phase | Current NIST SP 800-61 Rev 3 phase for the incident. |
| Severity | Combination of functional impact, information impact, recoverability, and regulatory impact. |
| Containment status | Active, partial, or complete, with evidence link. |
| Eradication evidence | Indicator removal, root cause patch, identity rotation records. |
| Recovery validation | Health check, synthetic transaction, and stakeholder sign-off. |
| Lessons learned | Owner, due date, and acceptance criteria for corrective actions. |

## Implementation Notes

- Document containment decisions even when no action is taken, so the rationale is auditable.
- Capture forensic artefacts with chain of custody records sufficient for regulatory or legal review.
- Coordinate all customer-facing statements with legal, privacy, and communications before release.
- Hold a blameless post-incident review within ten business days of recovery and publish findings internally.
- Tie lessons learned to the corrective action programme; do not let them remain recommendations only.

## Companion Documents

- NIST SP 800-61 Rev 3 (canonical)
- NIST SP 800-86 (Guide to Integrating Forensic Techniques into Incident Response)
- NIST SP 800-184 (Guide for Cybersecurity Event Recovery)
- ISO/IEC 27035-1 and 27035-2 (Information security incident management)
- ENISA CSIRT maturity framework
