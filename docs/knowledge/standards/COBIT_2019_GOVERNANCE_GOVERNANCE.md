---
title: COBIT 2019 Governance and Management Objectives Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISACA COBIT 2019 (2018-12-17) — "Governance and Management Objectives"; COBIT 2019 Design Guide; COBIT 2019 Implementation Guide; https://www.isaca.org/resources/cobit
---

# COBIT 2019 Governance and Management Objectives Governance

## Scope

This card governs how `orchords-docs` evaluates IT governance decisions against COBIT 2019 governance and management objectives. It is binding for any KB card that touches process design, RACI, or risk management.

## Why this card exists

COBIT 2019 organizes IT governance into 40 governance and management objectives across five domains. KB expansion that touches any of these domains must cite the COBIT objective it satisfies; without a citation, the KB can recommend a process that conflicts with the broader governance framework.

## Five domains and 40 objectives

### EDM — Evaluate, Direct and Monitor (5 objectives)

| EDM # | Title | Project interpretation |
|---|---|---|
| EDM01 | Ensured Governance Framework Setting and Maintenance | this card; governance cycle |
| EDM02 | Ensured Benefits Delivery | every KB card must declare its benefit class |
| EDM03 | Ensured Risk Optimization | `NIST_SP_800_30_R1_RISK_ASSESSMENT_GOVERNANCE.md` is the per-control reference |
| EDM04 | Ensured Resource Optimization | cost is recorded against each KB card |
| EDM05 | Ensured Stakeholder Transparency | review record in `REVIEWER_REVIEW_RECORD_RETENTION.md` |

### APO — Align, Plan and Organize (14 objectives)

| APO # | Title | Project interpretation |
|---|---|---|
| APO01 | Managed I&T Management Framework | code-style enforcement (workflows) |
| APO02 | Managed Strategy | batch-by-batch expansion roadmap |
| APO03 | Managed Enterprise Architecture | reference architecture cards |
| APO04 | Managed Innovation | technology refresh cadence (180-day cycle) |
| APO05 | Managed Portfolio | KB card portfolio (`docs/knowledge/`) |
| APO06 | Managed Budget and Cost | not applicable at KB level |
| APO07 | Managed Human Resources | contributor onboarding card |
| APO08 | Managed Relationships | third-party / subprocessor cards |
| APO09 | Managed Service Agreements | DPA cards under `docs/knowledge/standards/` |
| APO10 | Managed Vendors | subprocessor cards |
| APO11 | Managed Quality | `python .github/scripts/check_docs.py` is the quality gate |
| APO12 | Managed Risk | `NIST_SP_800_30_R1_RISK_ASSESSMENT_GOVERNANCE.md` |
| APO13 | Managed Security | `NIST_SP_800_53A_REV5_ASSESSMENT_GOVERNANCE.md`, `ISO_IEC_27017_2015_CLOUD_GOVERNANCE.md` |
| APO14 | Managed Data | `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md` |

### BAI — Build, Acquire and Implement (11 objectives)

| BAI # | Title | Project interpretation |
|---|---|---|
| BAI01 | Managed Programs | the KB expansion program itself |
| BAI02 | Managed Requirements | KB card scope statement |
| BAI03 | Managed Solutions | architecture cards |
| BAI04 | Managed Availability and Capacity | not applicable at KB level |
| BAI05 | Managed Organizational Change | PR-based review |
| BAI06 | Managed IT Changes | PR-based change control |
| BAI07 | Managed IT Change Acceptance and Transitioning | staging-then-prod for reference architectures |
| BAI08 | Managed Knowledge | the KB itself |
| BAI09 | Managed Assets | KB card registry |
| BAI10 | Managed Configuration | `CODEOWNERS`, branch protection |
| BAI11 | Managed Projects | the KB expansion batches |

### DSS — Deliver, Service and Support (6 objectives)

| DSS # | Title | Project interpretation |
|---|---|---|
| DSS01 | Managed Operations | operational telemetry of referenced services |
| DSS02 | Managed Service Requests and Incidents | playbooks under `docs/knowledge/playbooks/` |
| DSS03 | Managed Problems | `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` |
| DSS04 | Managed Continuity | reference architecture cards |
| DSS05 | Managed Security Services | security cards |
| DSS06 | Managed Business Process Controls | not applicable at KB level |

### MEA — Monitor, Evaluate and Assess (4 objectives)

| MEA # | Title | Project interpretation |
|---|---|---|
| MEA01 | Managed Performance and Conformance Monitoring | validator + workflow metrics |
| MEA02 | Managed System of Internal Control | self-attestation cycle |
| MEA03 | Managed Compliance with External Requirements | ISO / NIST / IETF cross-reference cards |
| MEA04 | Managed Assurance | PR review |

References: `https://www.isaca.org/resources/cobit`.

## Design factors

COBIT 2019 introduces 11 design factors that govern the customization of the framework for an organization. The project documents the chosen value of each factor in this card:

| Factor | Value | Notes |
|---|---|---|
| 1. Enterprise strategy | niche knowledge-base publisher | governance focus is conformance + transparency |
| 2. Enterprise goals | information-quality leadership | KB cards are the primary product |
| 3. Risk profile | low | KB content only; no live systems |
| 4. I&T-related issues | consistent cross-reference, valid links | root cause: link rot |
| 5. Threat landscape | low | no production infrastructure |
| 6. Compliance requirements | NIST SSDF, ISO 27017/27018/27701, OASIS, IETF | codified under `docs/knowledge/standards/` |
| 7. Role of IT | n/a | KB is documentation, not a service |
| 8. Sourcing model | internal | `ORCHORDS.COM` token only |
| 9. I&T adoption methods | GitHub-based PR flow | codified |
| 10. Technology adoption | rolling, conservative | 180-day review cycle |
| 11. Enterprise size | small | single-owner project |

## Performance management

Every governance objective (40 of them) has a cascade:

- **Process goal** — what the process achieves.
- **Process metrics** — how the process is measured.
- **Outcome metrics** — what the customer experiences.

The KB expansion pipeline reports each metric via GitHub Insights: PR throughput, validator pass rate, review response time, card-link integrity.

## Mandatory pre-flight (before adopting a new control or process change)

1. Identify the COBIT objective(s) affected.
2. Document the change in the COBIT-mapping card (this card).
3. Update the affected reference card or playbook.
4. Open a PR; review by `ORCHORDS.COM` token.

## Self-attestation cycle

Every 180 days, the project must:

1. Walk all 40 COBIT objectives and confirm the project's mapping is current.
2. Walk the 11 design factors and confirm they still apply.
3. Update the next-review date.

## Sources

- COBIT 2019 Framework (Governance and Management Objectives): `https://www.isaca.org/resources/cobit`
- COBIT 2019 Design Guide: `https://www.isaca.org/bookstore/cobit-2019-design-guide/wdbp4dg1`
- COBIT 2019 Implementation Guide: `https://www.isaca.org/bookstore/cobit-2019-implementation-guide/wdbp4ig1`
- COBIT 2019 Risk Governance Framework (supplement): `https://www.isaca.org/`
