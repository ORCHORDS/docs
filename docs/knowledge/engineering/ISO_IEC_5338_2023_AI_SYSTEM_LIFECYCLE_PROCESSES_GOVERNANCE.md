# ISO/IEC 5338:2023 AI System Lifecycle Processes Governance

## Purpose

ISO/IEC 5338:2023, "Information technology — Artificial intelligence — AI system life cycle processes," defines the processes and process outcomes for AI systems throughout their life cycle, providing an AI-specific complement to the generic process model of ISO/IEC/IEEE 12207. The standard addresses AI-specific activities such as data management, model development, model evaluation, deployment, monitoring, and retirement that are not directly covered by 12207. This article governs how engineering teams use ISO/IEC 5338 to plan and execute the AI system life cycle with the discipline the standard requires.

## Scope

The standard applies to AI systems at any life-cycle stage. Within this knowledge base, the article covers the AI-specific processes and their outcomes, the relationship between 5338 and 12207, the application of the processes to AI development and operation, and the documentation of process outputs. It does not cover the substantive AI methods (machine learning algorithms, neural network architectures) used in any specific project; those are governed by their own technical literature.

## Workflow

1. Apply the agreement, organizational, and technical management processes of ISO/IEC/IEEE 12207 as the base process model.
2. Add the AI-specific processes of ISO/IEC 5338:
   - AI system inception and scope definition: identify the AI system's purpose, stakeholders, success criteria, and constraints.
   - AI data management: data acquisition, quality assessment, labeling, augmentation, bias assessment, and data lifecycle.
   - AI model development: model selection, training, hyperparameter tuning, validation against held-out data, and reproducibility controls.
   - AI model evaluation: performance metrics appropriate to the application, fairness metrics, robustness and adversarial testing, explainability assessment.
   - AI system verification and validation: confirmation that the system meets its requirements and that the requirements address stakeholder needs.
   - AI system deployment: integration into the operational environment, transition planning, user training, and rollback provisions.
   - AI system operation and monitoring: ongoing performance, drift detection, incident response, and feedback loops.
   - AI system maintenance and improvement: model retraining, performance tuning, and the maintenance discipline that distinguishes data and model changes from system code changes.
   - AI system retirement: decommissioning, data archival or destruction, and stakeholder communication.
3. Document each process outcome. The standard names specific outcomes for each process; projects should track them explicitly.
4. Integrate the AI-specific processes with the project's quality plan and configuration management plan.

## Controls and evidence

Process evidence includes the AI system inception record, the data sheet, the model card, the evaluation report, the deployment plan, the monitoring records, the maintenance log, and the retirement record. Each artifact should be traceable to its AI process and to the corresponding outcome in the standard. Reproducibility evidence (random seeds, code versions, data versions) supports the model development process.

## Validation

Validation should confirm the AI-specific processes were applied, the process outcomes are documented, the artifacts (data sheet, model card, evaluation report) are produced and maintained, the deployment and monitoring records are continuous, and the AI-specific processes are integrated with the project's 12207 baseline. Spot checks should confirm reproducibility by re-running a model with documented seeds and data versions.

## Failure correction

Common failure modes: AI processes are reduced to "develop model" and "deploy" without the data, evaluation, and monitoring activities the standard requires (corrective: introduce the missing activities and produce the corresponding artifacts); process outcomes are produced but not linked to the standard's clauses (corrective: map each artifact to its process and outcome); maintenance changes are not distinguished from system changes (corrective: use separate change-control paths for data, model, and code changes and version each independently).

## Limitations

ISO/IEC 5338 defines the AI life-cycle processes; it does not prescribe the technical methods for any process. The standard does not guarantee the AI system is correct or safe; it ensures the AI-specific processes are applied with discipline. Sector overlays (e.g., medical, automotive) may impose additional requirements on AI processes; this article addresses the common base.

## Scope note

This article summarizes project-neutral engineering use of ISO/IEC 5338:2023. It does not assert any specific project's AI process conformance or claim any AI system outcome.

## Canonical sources

- ISO/IEC 5338:2023 — Information technology — Artificial intelligence — AI system life cycle processes: https://www.iso.org/standard/86607.html
- ISO/IEC/IEEE 12207:2024 — Systems and software engineering — Software life cycle processes: https://www.iso.org/standard/86916.html