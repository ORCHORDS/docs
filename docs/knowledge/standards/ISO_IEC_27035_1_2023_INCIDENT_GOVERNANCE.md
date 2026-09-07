# ISO/IEC 27035-1:2023 Information Security Incident Management Governance

## 1. Scope

This card governs ORCHORDS adoption of ISO/IEC 27035-1:2023 ("Information technology — Security techniques — Information security incident management — Part 1: Principles and process") for the planning, detection, response, and learning phases of the security incident lifecycle. It supersedes the 2016 first-edition guidance and aligns with ISO/IEC 27035-2 (2023) and ISO/IEC 27035-3 (2020).

## 2. Normative references

- ISO/IEC 27035-1:2023 — Principles and process.
- ISO/IEC 27035-2:2023 — Guidelines to plan and prepare for incident response.
- ISO/IEC 27035-3:2020 — Guidelines for ICT incident response operations.
- NIST SP 800-61 Rev. 3 (incident response) for US-sector alignment.
- ISO/IEC 27001:2022 Annex A.5.24–A.5.28 incident management controls.

## 3. Lifecycle phases (per ISO/IEC 27035-1 §6)

1. **Plan and prepare** — define incident management policy, roles, escalation matrix, and tooling.
2. **Detection and reporting** — capture events from SIEM, EDR, cloud audit, and customer reports.
3. **Assessment and decision** — classify (P1-P5), scope, decide whether to activate the IR team.
4. **Response** — contain, eradicate, recover, and preserve evidence.
5. **Lessons learned** — post-incident review within 5 business days of closure.

## 4. Roles and responsibilities

| Role | Responsibility | Authority |
| --- | --- | --- |
| Incident Commander (IC) | Overall response coordination, external comms | Page-and-go authority during the incident |
| Security Lead | Triage, classification, forensic integrity | Declares severity; cannot unilaterally downgrade |
| Service Owner | Service-level containment, customer comms | Approves service-impacting changes |
| Legal & Privacy | Regulatory disclosure timing | Approves regulator/regulator-body notifications |
| Communications | Customer and public messaging | Single source of truth for status page |
| Scribe | Timeline, decisions, evidence log | Read access to all incident channels |

## 5. Severity and SLAs

| Severity | Definition | Acknowledge | Contain | Notify |
| --- | --- | --- | --- | --- |
| P1 | Confirmed active breach with customer impact | 15 min | 4 h | 24 h to controllers; 72 h to authorities where required |
| P2 | Likely breach, no confirmed customer impact | 30 min | 8 h | 48 h to controllers |
| P3 | Isolated incident, single service | 2 h | 24 h | Within weekly summary |
| P4 | Suspicious event, no impact | 8 h | n/a | Within monthly review |
| P5 | Drill / tabletop / purple team exercise | n/a | n/a | Internal only |

## 6. Evidence handling

- All artefacts are written to the incident evidence bucket with **write-once-read-many** (object lock) retention.
- Chain-of-custody is captured in the Scribe's timeline entry; missing entries trigger a lessons-learned action item.
- Forensic images follow NIST SP 800-86 guidance.

## 7. Post-incident review

- Mandatory for P1-P3 within 5 business days of incident closure.
- Output: blameless postmortem with contributing factors, detection latency, containment latency, and corrective actions tracked in the risk register.
- Severe or recurring patterns trigger a mandatory standards-card or reference-card update.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. ISO/IEC 27035 revisions trigger out-of-cycle updates.
