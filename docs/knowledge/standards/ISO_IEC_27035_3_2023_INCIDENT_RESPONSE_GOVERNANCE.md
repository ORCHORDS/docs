# ISO/IEC 27035-3 Incident Response Operations Governance

## 1. Scope

This card governs the operational ICT incident response programme of ORCHORDS-managed systems by binding ISO/IEC 27035-3 to the broader ISO/IEC 27035 incident management series. It applies to detection, triage, analysis, containment, eradication, recovery, and post-incident activity for information security incidents affecting ORCHORDS production, customer data, and managed environments.

## 2. Normative references

- ISO/IEC 27035-3 (Guidelines for ICT incident response operations).
- ISO/IEC 27035-1:2023 (Principles and process).
- ISO/IEC 27035-2:2023 (Guidelines to plan and prepare for incident response).
- NIST SP 800-61 Rev. 3 (Incident response).
- ISO/IEC 27001:2022 and ISO/IEC 27002:2022 (ISMS controls).

## 3. Roles and responsibilities

| Role | Responsibility |
| --- | --- |
| Incident commander | Owns the response lifecycle for a declared incident. |
| Technical lead | Coordinates containment, eradication, and recovery actions. |
| Communications lead | Manages internal, customer, and regulator notifications. |
| Scribe | Maintains the incident timeline and decision log. |
| Legal and privacy | Advises on disclosure obligations and evidence handling. |

## 4. ICT incident response lifecycle

1. **Preparation.** Maintain runbooks, on-call rotations, tooling access, evidence kits, and pre-approved communications templates.
2. **Detection and reporting. **Collect alerts from SIEM, EDR, cloud audit logs, user reports, and threat intelligence; record the initial report with timestamp and source.
3. **Triage and assessment.** Confirm the event, classify severity, scope the affected assets, and decide whether to escalate to a declared incident.
4. **Containment.** Apply short-term containment (isolate host, revoke credentials, block traffic) and long-term containment (patch, rebuild segment) with explicit rollback criteria.
5. **Eradication.** Remove attacker artefacts, close the initial access path, rotate secrets, and confirm persistence is broken.
6. **Recovery.** Restore service from trusted sources, validate integrity, monitor for recurrence, and return the system to normal operation.
7. **Post-incident activity.** Produce a written post-incident review, capture lessons learned, and feed corrective actions into risk treatment and change management.

## 5. Evidence and decision handling

- Capture timestamps in UTC, source identifiers, and analyst identity for every action.
- Preserve volatile evidence (memory, network state) before reimaging.
- Maintain a decision log with rationale for containment choices that affect availability.
- Chain-of-custody for any artefact that may be needed for regulatory disclosure or legal action.

## 6. Coordination with adjacent frameworks

- ISO/IEC 27001 ISMS: incident outcomes feed risk treatment and management review.
- ISO/IEC 27035-1 process: lifecycle steps align with the plan-do-check-act structure.
- NIST SP 800-61: terminology and severity classes are aligned to avoid ambiguity.
- ISO/IEC 29147 and ISO/IEC 30111: vulnerabilities discovered during incidents are handed off to the disclosure process.

## 7. Training and exercises

- Annual tabletop for declared-incident decision making.
- Semi-annual functional exercise for containment and eradication.
- Post-incident review within 10 business days of closure for any Severity 1 or Severity 2 incident.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
