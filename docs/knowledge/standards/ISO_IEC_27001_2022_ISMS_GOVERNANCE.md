---
title: ISO/IEC 27001:2022 Information Security Management System (ISMS) Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 27001:2022 (October 2022) — Information security, cybersecurity and privacy protection — Information security management systems — Requirements; https://www.iso.org/standard/27001
---

# ISO/IEC 27001:2022 Information Security Management System (ISMS) Governance

## Scope

This card governs how `orchords-docs` evaluates ISO/IEC 27001:2022 ISMS requirements. It is the reference input for any KB card that touches Annex A controls (now 93 in v2022), the Statement of Applicability (SoA), or ISMS certification scope.

## Why this card exists

ISO/IEC 27001:2022 (October 2022) supersedes 2013 with restructured Annex A (now 93 controls grouped into 4 themes) and updated clauses 4–10. Without an explicit card, the KB cites 27001:2013 controls that no longer map to 27001:2022 Annex A.

## Document set

- **ISO/IEC 27001:2022** (October 2022) — ISMS requirements.
- **ISO/IEC 27002:2022** — Annex A control guidance.
- **ISO/IEC 27003** — implementation guidance.
- **ISO/IEC 27004** — monitoring and measurement.

References: `https://www.iso.org/standard/27001`.

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

## Annex A — 93 controls in 4 themes

| Theme | # controls |
|---|---|
| A.5 Organizational | 37 |
| A.6 People | 8 |
| A.7 Physical | 14 |
| A.8 Technological | 34 |

## Statement of Applicability (SoA)

The SoA is the canonical document that records:

- Each Annex A control.
- Whether the control is applicable.
- The justification.
- The implementation status.
- The control owner.

The SoA is mandatory for certification.

## Risk assessment

ISO/IEC 27001:2022 requires:

1. Define a risk methodology.
2. Identify risks.
3. Analyze risks.
4. Evaluate risks.
5. Select risk treatment options.
6. Determine controls.
7. SoA.

References: ISO/IEC 27005:2022 (risk management).

## Certification lifecycle

| Phase | Activity |
|---|---|
| Stage 1 audit | documentation review |
| Stage 2 audit | implementation review |
| Surveillance audit | annual (year 1, year 2) |
| Recertification audit | every 3 years |

## Mapping to other standards

| Standard | Mapping |
|---|---|
| NIST CSF 2.0 | per ISO mapping |
| NIST SP 800-53 Rev. 5 | per ISO mapping |
| CIS Controls v8 | per CIS mapping |
| SOC 2 (TSC 2017) | per AICPA mapping |

## Cross-reference

| Domain | Card |
|---|---|
| Privacy | `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md` |
| Risk | `ISO_IEC_27005_2022_RISK_GOVERNANCE.md` |
| Cloud | `ISO_IEC_27017_2015_CLOUD_GOVERNANCE.md` |
| PII | `ISO_IEC_27018_2019_PII_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches Annex A.
2. Confirm the control is in the SoA.
3. Update the next-review date.

## Sources

- ISO/IEC 27001:2022: `https://www.iso.org/standard/27001`
- ISO/IEC 27002:2022: `https://www.iso.org/standard/75652.html`
- ISO/IEC 27005:2022: `https://www.iso.org/standard/80585.html`
