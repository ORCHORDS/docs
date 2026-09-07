# ISO/IEC 42001:2023 AI Management System (AIMS) Governance

## Purpose

ISO/IEC 42001:2023 (first edition, 2023-12-18) specifies the requirements for establishing, implementing, maintaining, and continually improving an Artificial Intelligence Management System (AIMS). It is the first globally recognised AI management-system standard and aligns with ISO/IEC 27001 (ISMS) and ISO/IEC 9001 (QMS). Governance ensures that ORCHORDS sites that develop, integrate, or operate AI systems apply a documented AIMS that produces a statement of applicability, demonstrates responsible AI practices, and aligns with EU AI Act (Regulation 2024/1689) harmonised-standard expectations.

## Current context and source status

ISO/IEC 42001:2023 was published on 2023-12-18 and is the candidate harmonised standard for the EU AI Act conformity-assessment regime. The standard uses the ISO high-level structure (HLS) shared with ISO/IEC 27001:2022. Treat the standard text as the canonical reference; this card is a governance overlay.

## Document structure (Clauses 4–10)

| Clause | Title | Project interpretation |
|---|---|---|
| 4 | Context of the organization | KB is published as a public artifact; "interested parties" = readers, auditors, contributors |
| 5 | Leadership | `ORCHORDS` token owner is top management; AIMS leadership accountability documented in role description |
| 6 | Planning | AIMS objectives, AI risk assessment, AI impact assessment documented per release |
| 7 | Support | resources, competence, awareness, communication, documented information |
| 8 | Operation | operational planning and control, AI impact assessment, AI system lifecycle, data for AI, third-party assurance |
| 9 | Performance evaluation | monitoring, measurement, analysis, internal audit, management review |
| 10 | Improvement | nonconformity, corrective action, continual improvement |

## Governance workflow and controls

### 1. AIMS scope and leadership

- Define the AIMS scope (which AI systems, which business units, which jurisdictions); publish the scope statement.
- Assign top-management accountability for the AIMS; record accountability in a named role.
- Integrate AIMS objectives with the ISMS (ISO/IEC 27001) and QMS (ISO/IEC 9001) where overlap exists.

### 2. AI policy (Clause 5.2 + Annex A.5.1)

- Publish an AI policy that states the organisation's commitment to responsible AI, transparency, fairness, accountability, and human oversight.
- Communicate the policy to all staff and to relevant external stakeholders; review the policy at least annually.
- Align the policy with documented ethical principles (OECD AI Principles, UNESCO Recommendation on the Ethics of AI, EU AI Act Article 4a principles).

### 3. AI risk assessment and impact assessment (Clause 6 + Annex A.6.2.1, A.6.2.2)

- Conduct an AI risk assessment for every in-scope AI system at design, deployment, and material-change milestones.
- Conduct an AI impact assessment before adopting a new AI system in a reference card; record the assessment outcome in the release ticket.
- Use a documented risk methodology that addresses: bias, explainability, robustness, privacy, safety, security, environmental impact, and societal impact.
- Document the risk treatment plan and the residual risk; align with the ISO/IEC 27005 risk methodology to avoid duplicated risk registers.

### 4. AI system lifecycle and acceptance (Annex A.6.1.2, A.6.2.3, A.6.2.4, A.6.2.5)

- Document data quality for AI (Annex A.6.3.1): data lineage, consent basis, bias testing, data-quality criteria.
- Document AI system acceptance: PR review plus staging evaluation before production rollout.
- Document AI system operation and monitoring: observability on every AI reference architecture.
- Document AI system retirement: decommission plan before adoption.

### 5. Transparency, human oversight, and data quality (Annex A.6.2.2, A.6.4)

- Document user-facing AI disclosure; ensure the disclosure is meaningful and not buried in terms of service.
- Implement human-oversight controls appropriate to the AI system risk class (low, limited, high, prohibited).
- For high-risk AI systems under the EU AI Act, implement Article 14 human-oversight controls: explainability, reversibility, intervention.

### 6. Third-party assurance (Annex A.6.6)

- Assess third-party AI components and model providers against documented AIMS criteria before integration.
- Document the assessment outcome in a third-party AI register; re-assess on every material change.

### 7. Statement of applicability and audit

- Produce and maintain an AIMS statement of applicability that maps each Annex A control to its applicability, implementation status, and justification.
- Conduct internal AIMS audits at least annually; align audit cadence with the ISMS internal audit cadence.
- Conduct management review at least annually; record the review outcome and the actions assigned.
- Pursue certification when the business case supports it; align the certification scope with the published AIMS scope.

References: ISO/IEC 42001:2023; ISO/IEC 27001:2022; ISO/IEC 27005:2022; ISO/IEC 9001:2015; EU AI Act (Regulation 2024/1689); OECD AI Principles; UNESCO Recommendation on the Ethics of AI; `https://www.iso.org/standard/81230.html`.
