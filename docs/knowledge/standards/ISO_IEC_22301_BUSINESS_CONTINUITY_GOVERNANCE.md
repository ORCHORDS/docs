---
title: ISO/IEC 22301:2019 Business Continuity Management System Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 22301:2019 (October 2019) — Security and resilience — Business continuity management systems — Requirements; https://www.iso.org/standard/75106.html
---

# ISO/IEC 22301:2019 Business Continuity Management System Governance

## Scope

This card governs how `orchords-docs` evaluates business continuity management against ISO/IEC 22301:2019. It is the reference input for any KB card that touches BCMS, business impact analysis, or recovery planning.

## Why this card exists

ISO/IEC 22301:2019 (October 2019) supersedes 2012 with clarified lifecycle phases and PDCA structure. Without an explicit card, the KB cites 22301:2012 BCMS practices that no longer match 22301:2019 clauses.

## Document set

- **ISO/IEC 22301:2019** (October 2019) — BCMS requirements.
- **ISO/IEC 22313:2020** — BCMS guidance.
- **ISO 22317:2021** — BIA guidance.

References: `https://www.iso.org/standard/75106.html`.

## Clauses (4–10)

| Clause | Title |
|---|---|
| 4 | Context of the organization |
| 5 | Leadership |
| 6 | Planning |
| 7 | Support |
| 8 | Operation |
| 9 | Performance evaluation |
| 10 | Improvement |

## Business continuity lifecycle

The lifecycle phases:

1. **Anticipation** — risks and threats.
2. **Response** — incident response.
3. **Recovery** — restore business.
4. **Resumption** — return to normal.

References: ISO 22301 § 8.

## Mandatory pre-flight (before adopting BCMS controls)

1. The business impact analysis (BIA) is current.
2. The risk assessment is current.
3. The business continuity strategy is documented.
4. The BCMS plan is tested annually.
5. The BCMS plan is reviewed after every incident.

## Cross-reference

| Domain | Card |
|---|---|
| Incident | `NIST_SP_800_61_REV3_INCIDENT_GOVERNANCE.md`, `ISO_IEC_27035_INCIDENT_GOVERNANCE.md` |
| Risk | `ISO_IEC_27005_2022_RISK_GOVERNANCE.md` |
| Playbook | `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches BCMS.
2. Confirm the BIA is current.
3. Confirm the BCMS plan is tested.
4. Update the next-review date.

## Sources

- ISO/IEC 22301:2019: `https://www.iso.org/standard/75106.html`
- ISO/IEC 22313:2020: `https://www.iso.org/standard/76824.html`
- ISO 22317:2021: `https://www.iso.org/standard/80801.html`
