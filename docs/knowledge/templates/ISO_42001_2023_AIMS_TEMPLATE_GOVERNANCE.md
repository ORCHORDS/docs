# ISO/IEC 42001:2023 AI Management System (AIMS) Template Governance

## Purpose
Establish the governance pattern for templating an Artificial Intelligence Management System (AIMS) per ISO/IEC 42001:2023 (Information technology — Artificial intelligence — Management system), including AI policy, risk assessment, and impact assessment.

## Scope
Applies to every AI system developed, deployed, or operated by the studio, regardless of model class (generative, predictive, classification) or deployment mode (cloud, on-premises, edge).

## Workflow
1. Use a templated AIMS document set with mandatory elements per ISO/IEC 42001:2023: AI policy, objectives, scope statement, risk assessment methodology, and impact assessment methodology.
3. For each AI system, conduct an AI risk assessment identifying stakeholders, harms, likelihood, severity, and mitigations; document the assessment using the studio's standardized risk template.
5. Conduct an AI impact assessment for each system that affects natural persons or makes decisions with significant effects; document the assessment per ISO/IEC 42001:2023 Annex A controls.
7. Maintain an AI system inventory with model identifier, training data lineage, intended use, and operational boundaries.
9. Plan AI system lifecycle management: development, validation, deployment, operation, retirement, with explicit documentation requirements at each phase.

## Controls and evidence
- AI policy and objectives with owner, measurable target, and review cadence.
- AI risk register with stakeholder, harm category, likelihood, severity, mitigation, and residual risk.
- AI impact assessment records with decision context, affected parties, and mitigation measures.
- AI system inventory with model identifier, training data lineage, intended use, and operational boundaries.

## Validation
- Re-validate the AI risk register against the latest impact assessments and confirm all identified harms have mitigation owners.
- Verify that each AI system has a documented intended use statement and that the operational boundaries match the deployment configuration.
- Confirm that training data lineage is traceable to source datasets and that consent / licensing obligations are documented.

## Failure correction
- **AI risk assessment outdated** → re-run the assessment, document the changes, and update the AI risk register.
- **AI impact assessment missing for a high-risk system** → suspend deployment of the system, document the gap, and complete the impact assessment before resuming.
- **Training data lineage broken** → suspend model retraining on the affected dataset, document the break, and remediate the source data provenance.

## Limitations
- ISO/IEC 42001:2023 is a management system standard; it does not define AI technical controls (refer to ISO/IEC 23894:2023 for AI risk management guidance and ISO/IEC 27090 for AI security).
- Some jurisdictions impose additional requirements (e.g., EU AI Act); integrate regional requirements into the AIMS where applicable.
- AI system behaviour may evolve through continued training; re-validate the impact assessment periodically.

## Scope note
This article is part of the templates leaf. Cross-reference: NIST_SP_800_53A_REV5_ASSESSMENT_PROCEDURE_TEMPLATE_GOVERNANCE.md, ISO_9001_2015_QUALITY_MANAGEMENT_SYSTEM_TEMPLATE_GOVERNANCE.md, ISO_27018_CLOUD_PII_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- ISO/IEC 42001:2023 — Information technology — Artificial intelligence — Management system: https://www.iso.org/standard/81230.html
- ISO/IEC 23894:2023 — Information technology — Artificial intelligence — Guidance on risk management: https://www.iso.org/standard/77304.html
- ISO/IEC 27001:2022 — Information security, cybersecurity and privacy protection — Information security management systems — Requirements: https://www.iso.org/standard/27001
- ISO/IEC 27018:2019 — Code of practice for protection of personally identifiable information in public clouds acting as PII processors: https://www.iso.org/standard/76559.html
- EU AI Act — Regulation (EU) 2024/1689: https://eur-lex.europa.eu/eli/reg/2024/1689/oj