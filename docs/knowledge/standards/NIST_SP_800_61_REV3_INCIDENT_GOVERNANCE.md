---
title: NIST SP 800-61 Rev. 3 (Draft) Incident Response Recommendations Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-61 Rev. 3 (Draft, April 2025) — Incident Response Recommendations and Considerations for Cybersecurity Risk Management; https://csrc.nist.gov/publications/detail/sp/800-61/rev-3/draft
---

# NIST SP 800-61 Rev. 3 (Draft) Incident Response Recommendations Governance

## Scope

This card governs how `orchords-docs` evaluates incident response (IR) against NIST SP 800-61 Rev. 3 (Draft). It is the reference input for any KB card that touches incident handling, IR plan structure, or incident coordination.

## Why this card exists

NIST SP 800-61 Rev. 3 (Draft, April 2025) supersedes Rev. 2 (2012) with a reframe toward CSF 2.0 alignment, governance, and continuous improvement. Without an explicit card, the KB cites the legacy Rev. 2 lifecycle (Preparation → Detection → Containment → Eradication → Recovery → Lessons Learned) that no longer matches the draft.

## Document set

- **NIST SP 800-61 Rev. 3 (Draft)** (April 2025) — current draft.
- **NIST SP 800-61 Rev. 2** (August 2012) — legacy cycle.
- **NIST CSF 2.0** — RESPONSE function.

References: `https://csrc.nist.gov/publications/detail/sp/800-61/rev-3/draft`.

## Process (Rev. 3 draft)

Rev. 3 reframes IR around CSF 2.0:

- **GOVERN** — establish IR governance, roles, and policy.
- **IDENTIFY** — asset, data, and system inventory.
- **PROTECT** — preventative controls, awareness, training.
- **DETECT** — anomalies, monitoring, adverse events.
- **RESPOND** — incident management, analysis, mitigation, communication.
- **RECOVER** — recovery planning, improvements.

## Incident classification

| Severity | Description |
|---|---|
| Catastrophic | full outage, data breach with regulatory impact |
| Major | partial outage, data exposure |
| Moderate | degraded service, contained incident |
| Minor | local incident, no service impact |
| Low | false positive, near-miss |

## Incident response plan

A NIST-aligned IR plan contains:

1. Mission, scope, and authority.
2. Roles and responsibilities (CISO, IR lead, comms lead, legal).
3. Coordination with external entities (US-CERT, FBI, ISAC).
4. Communication protocols (internal, external, regulatory).
5. Severity classification.
6. Containment, eradication, recovery procedures.
7. Evidence handling.
8. Lessons-learned and continuous improvement.

## Mandatory pre-flight (before declaring an IR plan valid)

1. The IR plan is approved by executive leadership.
2. The IR team has at least 4 named roles.
3. The IR plan has been tested via tabletop.
4. The IR plan is updated annually.
5. The IR plan is integrated with NIST CSF 2.0 GOVERN function.

## Cross-reference

| Domain | Card |
|---|---|
| CSF | `NIST_CSF_2_2024_GOVERNANCE.md` |
| 800-53 | `NIST_SP_800_53_R5_SECURITY_GOVERNANCE.md` |
| Privacy | `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md` |
| Playbook | `PRIVACY_INCIDENT_RESPONSE_PLAYBOOK.md`, `SUPPLY_CHAIN_INCIDENT_PLAYBOOK.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches IR.
2. Confirm the CSF 2.0 mapping is current.
3. Confirm the IR plan is updated.
4. Update the next-review date.

## Sources

- NIST SP 800-61 Rev. 3 Draft: `https://csrc.nist.gov/publications/detail/sp/800-61/rev-3/draft`
- NIST SP 800-61 Rev. 2: `https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final`
- NIST CSF 2.0: `https://www.nist.gov/cyberframework`
- CISA IR: `https://www.cisa.gov/news-events/directives/incident-response`
