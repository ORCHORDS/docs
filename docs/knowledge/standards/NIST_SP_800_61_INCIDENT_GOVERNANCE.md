---
title: NIST SP 800-61 Rev. 2 Computer Security Incident Handling Guide Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-61 Rev. 2 (August 2012) — Computer Security Incident Handling Guide; https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final
---

# NIST SP 800-61 Rev. 2 Computer Security Incident Handling Guide Governance

## Scope

This card governs how `orchords-docs` evaluates incident handling against NIST SP 800-61 Rev. 2. It is the reference input for every incident-response playbook under `docs/knowledge/playbooks/`.

## Why this card exists

NIST SP 800-61 is the de-facto incident handling guide for US federal agencies and the broader NIST ecosystem. It organizes incident handling into four phases: preparation; detection and analysis; containment, eradication, and recovery; and post-incident activity. Without an explicit card, the KB cites incident response practices that do not survive NIST-aligned audit.

## Document set

- **NIST SP 800-61 Rev. 2** — Computer Security Incident Handling Guide (August 2012).
- Note: SP 800-61 Rev. 3 is in development (2026-09 status: draft). The current card tracks Rev. 2; a Rev. 3 card will follow when published.

References: `https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final`.

## Four-phase process

### Phase 1 — Preparation

- Establish incident response policy.
- Establish communication channels.
- Train the response team.
- Acquire tooling (SIEM, EDR, log retention, forensic tools).

### Phase 2 — Detection and analysis

- Detect: monitor for indicators (signature-based, behavioral, anomaly-based).
- Analyze: confirm the event is an incident.
- Prioritize: assign severity (low, medium, high, critical).
- Notify: per the communication plan.

### Phase 3 — Containment, eradication, and recovery

- Containment: short-term (isolate, deny network) and long-term (rebuild, segment).
- Eradication: remove malware, patch vulnerabilities, reset credentials.
- Recovery: restore service from clean backup; validate integrity.

### Phase 4 — Post-incident activity

- Lessons-learned review (per `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`).
- Update the incident response policy.
- Update tooling and detection rules.
- Document follow-up actions.

## Incident categories

NIST categorizes incidents by:

- **Category** (e.g., denial of service, malicious code, unauthorized access, inappropriate usage, multiple components).
- **Severity** (low / medium / high) based on impact and recoverability.
- **Type** of impact (e.g., data exfiltration, data destruction, data modification, system downtime).

## Incident response team structure

| Role | Responsibility |
|---|---|
| Incident Manager | leads the response |
| Security Analyst | technical investigation |
| Forensic Analyst | evidence collection, preservation |
| Threat Intelligence Analyst | intel correlation |
| Communications Lead | external comms |
| Legal Counsel | regulatory compliance |
| HR | insider-incident coordination |
| IT Operations | containment and recovery |

## Communication plan

- Internal: incident channel, executive escalation.
- External: customers, partners, regulators, law enforcement, media.
- Templates: pre-drafted per audience.

## Mandatory pre-flight (before adopting a new incident-handling practice)

1. The four phases are documented.
2. Roles are assigned.
3. Communication plan is documented.
4. Tooling is wired.
5. Severity classification is documented.

## Cross-reference

| Domain | Card |
|---|---|
| ISO 27035 | `ISO_IEC_27035_2016_INCIDENT_GOVERNANCE.md` |
| Privacy | `PRIVACY_INCIDENT_RESPONSE_PLAYBOOK.md` |
| Post-incident | `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` |
| Vulnerability disclosure | `ISO_IEC_30111_2019_VDP_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every incident-handling playbook.
2. Confirm conformance to the four phases.
3. Confirm roles and communication plan are current.
4. Update the next-review date.

## Sources

- NIST SP 800-61 Rev. 2: `https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final`
- NIST SP 800-184 (Guide for Cybersecurity Event Recovery): `https://csrc.nist.gov/publications/detail/sp/800-184/final`
- CISA Incident Response: `https://www.cisa.gov/incident-response`
- ENISA CSIRT services: `https://www.enisa.europa.eu/topics/csirt-cert-services`
