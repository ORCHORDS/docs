# ISO/IEC 5338:2023 AI System Lifecycle Governance

## Purpose

ISO/IEC 5338:2023, *Information technology — Artificial intelligence — AI system lifecycle process*, defines a process framework for AI systems across their lifecycle — from concept and development through deployment, operation, and retirement — complementing 12207-style software lifecycle processes with AI-specific considerations (data, models, evaluation, evolution).

AI development teams should apply 5338's process model so that AI-specific lifecycle stages (data preparation, model training, evaluation against AI-specific criteria) are governed processes with defined outputs, not informal practices squeezed into a software lifecycle template.

## Scope

Applies to the studio's AI system development and operation. Covers the AI lifecycle process framework, AI-specific process activities, and documentation obligations. Does not cover AI management systems (ISO/IEC 42001) or AI risk management method (ISO/IEC 23894).

## Workflow

1. Map the AI system lifecycle per 5338's process model: concept, development (data, model, evaluation), deployment, operation and monitoring, and retirement — each stage with defined entry/exit criteria and outputs.
2. Treat data as a first-class lifecycle artefact: data acquisition, preparation, and quality processes produce recorded outputs (datasets with lineage and quality measures), not informal preprocessing.
3. Govern model development: training, fine-tuning, and evaluation are processes with recorded configurations, datasets, and evaluation results — reproducibility is the entry criterion for promotion.
4. Evaluate against AI-specific criteria beyond ordinary test suites: performance on defined benchmarks, robustness, bias measures where applicable, and behavior under distribution shift — each with thresholds and recorded results.
5. Deploy with monitoring matched to AI failure modes: performance drift, data drift, and behavior anomalies monitored with defined responses; AI systems degrade silently where software fails loudly.
6. Manage evolution deliberately: retraining and model updates flow through the same promotion gates as initial deployment — evaluation, thresholds, approval — with rollback paths.
7. Retire with data and model disposition: retirement records what happens to training data, model artifacts, and downstream dependencies; AI retirement without disposition planning leaves orphaned models and data.

## Controls and evidence

- Lifecycle process definition mapped to 5338's stages with entry/exit criteria.
- Dataset records with lineage and quality measures.
- Model development records: configurations, training runs, evaluation results.
- AI-specific evaluation records with thresholds.
- Deployment monitoring configuration and drift response records.
- Retirement disposition records.

## Validation

- Sample one AI system: confirm each lifecycle stage has defined outputs and the records exist.
- Confirm evaluation results include AI-specific criteria with thresholds, not only functional tests.
- Confirm monitoring covers performance and data drift with defined responses.

## Failure correction

- **Stage output missing (e.g., dataset without lineage)** → reconstruct or re-create the artefact; unreconstructable lineage blocks promotion.
- **Evaluation without AI-specific criteria** → define and run the missing evaluations before the next promotion.
- **Retirement without disposition** → complete the disposition record and execute the plan for orphaned artifacts.

## Limitations

5338 defines the process frame; it does not prescribe evaluation thresholds, bias measurement methods, or domain-specific validation — those draw on 42001/23894 and domain practice. AI lifecycle practice is young; expect the framework's application to evolve as tooling and regulation mature.

## Scope note

This article is part of the engineering leaf. Cross-reference: `ISO_IEC_23894_2023_AI_RISK_MANAGEMENT_GOVERNANCE.md`, `ISO_42001_2023_AIMS_TEMPLATE_GOVERNANCE.md` (templates leaf), and `GENAI_SSDF_COMMUNITY_PROFILE.md`.

## Canonical sources

- ISO/IEC 5338:2023 — Information technology — Artificial intelligence — AI system lifecycle process: https://www.iso.org/obp/ui/#iso:std:iso-iec:5338:ed-1
- ISO/IEC 42001:2023 — AI management system: https://www.iso.org/obp/ui/#iso:std:iso-iec:42001:ed-1
- ISO/IEC 23894:2023 — AI — Guidance on risk management: https://www.iso.org/obp/ui/#iso:std:iso-iec:23894:ed-1
- ISO/IEC/IEEE 12207:2017 — Software life cycle processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:12207:ed-2
- NIST AI Risk Management Framework (AI RMF 1.0): https://www.nist.gov/itl/ai-risk-management-framework
