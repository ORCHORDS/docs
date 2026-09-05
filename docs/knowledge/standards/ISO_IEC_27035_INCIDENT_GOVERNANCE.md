---
title: ISO/IEC 27035:2022 Incident Management Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 27035:2022 — Information security incident management; ISO/IEC 27035-1:2022 (Principles and process); ISO/IEC 27035-2:2022 (Guidelines for planning and preparation); ISO/IEC 27035-3:2022 (Guidelines for incident response operations); https://www.iso.org/standard/78973.html
---

# ISO/IEC 27035:2022 Incident Management Governance

## Scope

This card governs how `orchords-docs` evaluates information security incident management against ISO/IEC 27035:2022. It is the reference input for any KB card that touches incident handling, IR plan structure, or incident coordination.

## Why this card exists

ISO/IEC 27035:2022 supersedes 2011 with a restructured three-part standard aligned to ISO/IEC 27001:2022. Without an explicit card, the KB cites 27035:2011 incident stages that no longer map cleanly to the 2022 plan-and-prepare / response-and-learn model.

## Document set

- **ISO/IEC 27035-1:2022** — Principles and process.
- **ISO/IEC 27035-2:2022** — Guidelines for planning and preparation.
- **ISO/IEC 27035-3:2022** — Guidelines for incident response operations.

References: `https://www.iso.org/standard/78973.html`.

## Process overview

ISO/IEC 27035:2022 defines a four-phase model:

1. **Plan and prepare** — policy, plan, team, training.
2. **Identify and report** — detection, triage, classification.
3. **Assess and decide** — analysis, decision.
4. **Respond and learn** — containment, eradication, recovery, lessons learned.

## Roles

| Role | Responsibility |
|---|---|
| Incident manager | coordinate |
| Incident responder | execute |
| Communications lead | internal / external comms |
| Legal / privacy | regulatory impact |
| Forensic analyst | evidence |

## Severity classification

| Severity | Example |
|---|---|
| Critical | mass PII breach, ransomware with exfiltration |
| High | targeted intrusion, data destruction |
| Medium | isolated malware, contained leak |
| Low | phishing attempt, scan |

## Cross-reference

| Domain | Card |
|---|---|
| NIST IR | `NIST_SP_800_61_REV3_INCIDENT_GOVERNANCE.md` |
| Privacy | `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md` |
| ISMS | `ISO_IEC_27001_2022_ISMS_GOVERNANCE.md` |
| Playbook | `PRIVACY_INCIDENT_RESPONSE_PLAYBOOK.md`, `SUPPLY_CHAIN_INCIDENT_PLAYBOOK.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches IR.
2. Confirm the 27035 phase is identified.
3. Update the next-review date.

## Sources

- ISO/IEC 27035-1:2022: `https://www.iso.org/standard/78973.html`
- ISO/IEC 27035-2:2022: `https://www.iso.org/standard/78974.html`
- ISO/IEC 27035-3:2022: `https://www.iso.org/standard/78975.html`
