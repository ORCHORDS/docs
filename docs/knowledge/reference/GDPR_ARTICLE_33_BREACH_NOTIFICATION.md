---
title: "GDPR Article 33 Breach Notification"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Regulation (EU) 2016/679 (GDPR); https://eur-lex.europa.eu/eli/reg/2016/679/oj"
---

# GDPR Article 33 Breach Notification

## Scope

Reference card for Article 33 of Regulation (EU) 2016/679, the *General Data Protection Regulation* (GDPR), which establishes the breach-notification obligation for personal-data breaches. Profiles that govern personal-data processing in the EU should reference Article 33 explicitly and bind it to ISO/IEC 27035 incident management, NIST SP 800-61 incident handling, and the regulator-specific sectoral requirements (for example NIS2, DORA, sectoral regulators).

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | Regulation (EU) 2016/679 (GDPR) |
| Article | Article 33 (Breach notification to the supervisory authority) |
| Companion | Article 34 (Communication to the data subject), Article 32 (Security of processing), Article 5 (Principles), NIS2 Directive, DORA |
| Status | In force since May 2018; supplementary guidance issued by EDPB (current published version) |
| Source URL | https://eur-lex.europa.eu/eli/reg/2016/679/oj |

## Plan

1. Reference Article 33 by number whenever a profile governs personal-data breach handling in the EU.
2. Determine whether the incident is a personal-data breach under Article 4(12): a breach of security leading to the accidental or unlawful destruction, loss, alteration, unauthorized disclosure of, or access to personal data.
3. Apply the 72-hour notification timeline: notification to the supervisory authority within 72 hours of becoming aware of the breach, unless the breach is unlikely to result in a risk to natural persons.
4. Document the notification contents: nature of the breach, categories and approximate number of data subjects, categories and approximate number of records, name and contact details of the data protection officer, likely consequences, measures taken or proposed, and the data-protection impact assessment reference.
5. Apply Article 34 communication to the data subject when the breach is likely to result in a high risk to natural persons.
6. Maintain documentation of all personal-data breaches (Article 33(5)).
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- GDPR Articles 4(12) (definition), 5 (principles), 32 (security), 33 (notification to authority), 34 (notification to data subject), 35 (DPIA).
- EDPB Guidelines 9/2022 (personal data breach notification examples) and related EDPB guidance.
- ISO/IEC 27035-1:2023 Incident Management Governance; NIST SP 800-61 Incident Handling.
- Internal incident-response policy, breach-response runbook, and breach register.

## ORCHORDS Profile

ORCHORDS treats Article 33 as a binding obligation for personal-data breaches in the EU. Profiles that reference personal-data breach handling should cite Article 33 by number, identify the 72-hour timeline and the notification contents, and bind to ISO/IEC 27035, NIST SP 800-61, and the regulator-specific requirements.

A profile that references "personal data breach" without binding to GDPR Article 33 / Article 34 is non-conformant.

## Implementation Notes

- The 72-hour clock starts at the moment the controller becomes aware of the breach, not at the moment the breach occurred.
- "Awareness" requires reasonable certainty that a breach has occurred; speculative investigation does not start the clock.
- The notification can be phased: an initial notification within 72 hours followed by updates as the investigation progresses.
- The "documentation of all personal-data breaches" (Article 33(5)) requires a breach register regardless of whether the breach is notified.
- For multinational operations, multiple supervisory authorities may have jurisdiction; the lead supervisory authority is determined by Article 56.

## Companion Documents

- [ISO/IEC 27035-1:2023 Incident Management Governance](../standards/ISO_IEC_27035_1_INCIDENT_MANAGEMENT_GOVERNANCE.md)
- [NIST SP 800-61 Incident Handling Governance](../standards/NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md)
- [Cybersecurity Incident Response Playbook](../playbooks/CYBERSECURITY_INCIDENT_RESPONSE.md)
- [Data Loss Prevention Response Playbook](../playbooks/DATA_LOSS_PREVENTION_RESPONSE.md)
