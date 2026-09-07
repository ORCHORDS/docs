# ISO/IEC 38507:2022 AI Governance Implications for IT Governance Governance

## 1. Scope

This card governs ORCHORDS adoption of ISO/IEC 38507:2022 ("Information technology — Governance of IT — Governance implications of the use of artificial intelligence by organizations"). It applies to the design, deployment, and oversight of AI systems that materially affect stakeholders (employees, customers, citizens, suppliers).

## 2. Normative references

- ISO/IEC 38507:2022.
- ISO/IEC 38500:2015 — Corporate governance of IT.
- ISO/IEC 42001:2023 — AI management system (AIMS).
- EU AI Act (Regulation (EU) 2024/1689).
- NIST AI Risk Management Framework 1.0 and Generative AI Profile (NIST AI 600-1).

## 3. Six governance principles

1. **Responsibility**: clear assignment of AI decision rights across the three lines of defence.
2. **Strategy**: AI initiatives must align with the corporate strategy and be traceable to the board-level risk appetite.
3. **Acquisition**: AI components (models, datasets, services) are procured with documented due diligence, including provenance and licensing.
4. **Performance**: AI systems are monitored continuously for business value, fairness, and unintended harm.
5. **Conformance**: AI systems comply with applicable laws, regulations, and internal policies.
6. **Human behaviour**: human oversight, training, and accountability shape AI deployment and use.

## 4. Three-lines accountability model

| Line | Role | AI-specific obligations |
| --- | --- | --- |
| First | Business units deploying AI | Operate within the documented AI use case; report incidents; collect feedback |
| Second | Risk, compliance, legal, AI ethics | Maintain the AI risk register; review model cards and data sheets; challenge the business |
| Third | Internal audit | Independent assurance over the AI governance framework; report to audit committee |

## 5. Required artefacts

- **AI use case intake** with intended purpose, affected stakeholders, and risk tier (low / medium / high / prohibited).
- **Model card** describing intended use, training data, evaluation results, limitations.
- **Data sheet** documenting provenance, licensing, consent, and known biases.
- **Impact assessment** for medium- and high-risk AI systems (algorithmic, fundamental rights, DPIA, environmental).
- **Post-deployment monitoring plan** with KPIs and SLOs.
- **Rollback procedure** to revert to a non-AI fallback within an SLO.

## 6. Decision rights matrix

| Decision | Owner | Escalation |
| --- | --- | --- |
| Approve a new AI use case | Business sponsor | Risk Council for medium+ risk |
| Approve a high-risk AI system | Risk Council | Executive Committee |
| Deploy a prohibited AI system | n/a — refused at intake | n/a |
| Modify a deployed high-risk model | Risk Council | Executive Committee |
| Disable an AI system in production | On-call SRE + Service Owner | Post-incident review |

## 7. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. ISO/IEC 38507 revisions, EU AI Act amendments, and major model-card or NIST AI profile releases trigger out-of-cycle updates.
