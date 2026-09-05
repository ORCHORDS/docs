---
title: ISO/IEC 27035:2016 Information Security Incident Management Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 27035-1:2016 (Principles and process); ISO/IEC 27035-2:2016 (Guidelines to plan and prepare for incident response); ISO/IEC 27035-3:2020 (Guidelines for incident response operations); https://www.iso.org/standard/60803.html, https://www.iso.org/standard/60804.html, https://www.iso.org/standard/77008.html
---

# ISO/IEC 27035:2016 Information Security Incident Management Governance

## Scope

This card governs how `orchords-docs` evaluates information security incident management against ISO/IEC 27035:2016 (3 parts). It is the reference input for every playbook under `docs/knowledge/playbooks/` that touches incident response.

## Why this card exists

ISO/IEC 27035 organizes incident management into a five-phase process: plan and prepare, detect and report, assess and decide, respond, and learn. A KB card that recommends an incident response procedure without binding to 27035 produces a playbook that does not survive a security audit.

## Document set

- **ISO/IEC 27035-1:2016** — Principles and process (replaces ISO/IEC 27035:2011).
- **ISO/IEC 27035-2:2016** — Guidelines to plan and prepare for incident response.
- **ISO/IEC 27035-3:2020** — Guidelines for incident response operations (new part).

References: `https://www.iso.org/standard/60803.html`, `https://www.iso.org/standard/60804.html`, `https://www.iso.org/standard/77008.html`.

## Five-phase process

### Phase 1 — Plan and prepare

- Establish incident management policy.
- Define roles, responsibilities, and authorities.
- Establish communication channels (internal + external).
- Plan training and awareness.
- Plan tooling (SIEM, EDR, log retention).

### Phase 2 — Detect and report

- Monitor events from SIEM, EDR, IDS/IPS.
- Triage alerts.
- Confirm incident.
- Open incident ticket with severity classification.

### Phase 3 — Assess and decide

- Classify incident by severity (low, medium, high, critical).
- Identify scope (which systems, which data, which users).
- Identify regulatory obligations (notification SLA per `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md`).
- Decide on response strategy (contain, eradicate, recover).

### Phase 4 — Respond

- Contain the incident (network segmentation, account disable).
- Eradicate the root cause (patch, credential reset).
- Recover from the incident (restore, validate).
- Communicate internally and externally.

### Phase 5 — Learn

- Conduct post-incident review (per `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`).
- Document lessons learned.
- Update incident management policy.
- Update tooling and detection rules.

References: ISO/IEC 27035-1:2016 § 6.

## Roles

| Role | Responsibility |
|---|---|
| Incident Manager | leads the incident response |
| Incident Coordinator | coordinates with stakeholders |
| Investigator | technical forensics, root cause |
| Communications Lead | external communications |
| Legal Counsel | regulatory compliance |
| Subject-Matter Expert | technical subject-matter input |
| Documenter | records timeline and actions |

## Severity classification

| Severity | Definition | Response SLA |
|---|---|---|
| Critical | widespread impact, data loss, regulatory notification | ≤ 1 hour to acknowledge, ≤ 4 hours to contain |
| High | significant impact, no data loss | ≤ 4 hours to acknowledge, ≤ 24 hours to contain |
| Medium | limited impact | ≤ 24 hours to acknowledge, ≤ 7 days to contain |
| Low | no operational impact | ≤ 7 days to acknowledge |

## Communication

- Internal communication: incident channel + status page.
- External communication: customer-facing status page, regulatory notifications.
- Communications are timestamped and archived.

## Mandatory pre-flight (before adopting a new incident response plan)

1. Roles are assigned per the policy table above.
2. Communication channels are documented.
3. Severity classification is documented.
4. Detection sources are wired (SIEM, EDR, IDS/IPS, anomaly detection).
5. Regulatory obligations are identified (GDPR Article 33, NIS2, HIPAA, PCI-DSS).
6. Post-incident review is scheduled.

## Cross-reference

| Domain | Card |
|---|---|
| Privacy incident | `PRIVACY_INCIDENT_RESPONSE_PLAYBOOK.md` |
| Post-incident review | `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` |
| Vulnerability disclosure | `ISO_IEC_30111_2019_VDP_GOVERNANCE.md` |
| AI incident | `ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md` |
| OT incident | `OT_SEGMENTATION_PLAYBOOK.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every incident-response playbook.
2. Confirm conformance to the 5-phase process.
3. Confirm severity classification is current.
4. Confirm roles are assigned.
5. Update the next-review date.

## Sources

- ISO/IEC 27035-1:2016: `https://www.iso.org/standard/60803.html`
- ISO/IEC 27035-2:2016: `https://www.iso.org/standard/60804.html`
- ISO/IEC 27035-3:2020: `https://www.iso.org/standard/77008.html`
- NIST SP 800-61 Rev. 2: `https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final`
- ENISA CSIRT services: `https://www.enisa.europa.eu/topics/csirt-cert-services`
