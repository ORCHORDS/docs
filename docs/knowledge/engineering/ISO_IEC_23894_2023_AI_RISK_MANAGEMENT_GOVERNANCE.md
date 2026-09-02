# ISO/IEC 23894:2023 AI Risk Management Governance

## Purpose

ISO/IEC 23894:2023, "Information technology — Artificial intelligence — Guidance on risk management," applies the principles and concepts of ISO 31000 to the development and deployment of AI systems, including guidance on risk identification, analysis, evaluation, treatment, communication, monitoring, and review across the AI life cycle. This article governs how engineering teams apply AI-specific risk management to AI projects so that AI risks are identified, treated, and tracked throughout the AI life cycle.

## Scope

The standard applies to organizations developing or deploying AI systems where risks specific to AI must be managed. Within this knowledge base, the article covers the AI life-cycle considerations, AI-specific risk sources (data, model, operational, ethical, societal), the application of ISO 31000 processes to AI, and the documentation of AI risk decisions. It does not cover sector-specific AI risk regimes (financial, automotive, medical); readers should consult their sector overlays.

## Workflow

1. Establish the AI risk management context: define the AI system boundary, identify the stakeholders, identify the applicable laws and standards, and articulate the organization's risk criteria and risk appetite for AI.
2. Identify AI risks. AI-specific risk sources include data quality and representativeness, model robustness and generalization, fairness and bias, explainability, security and adversarial resilience, safety in operational use, privacy, third-party components, and the societal impact of automated decisions.
3. Analyze and evaluate each identified AI risk: estimate likelihood and consequence using the project's chosen scheme, compare against the risk criteria, and assign a treatment priority.
4. Treat each risk according to the chosen risk treatment approach (avoid, reduce, transfer, accept) and design controls that reduce likelihood or consequence to acceptable levels.
5. Implement the controls within the AI life cycle: data management, model development, evaluation, deployment, monitoring, and decommissioning.
6. Monitor and review AI risks continuously. The AI system's behavior in operation may shift from training-time expectations; risk treatment must include post-deployment monitoring and incident response.
7. Communicate AI risk decisions to stakeholders and maintain records for accountability.

## Controls and evidence

Evidence that AI risk management is being applied includes the AI risk context, the AI risk register, the risk treatment plan and its execution, the AI life-cycle artifacts (data sheets, model cards, evaluation reports), and the post-deployment monitoring results. AI risks should be linked to specific controls and to specific life-cycle stages so that mitigation is verifiable.

## Validation

Validation should confirm the AI risk context is documented, the AI risk register covers AI-specific risk sources, the treatments address the identified risks, and the post-deployment monitoring covers model performance, fairness, and security. AI risk decisions should be reviewed at each major AI life-cycle milestone and after incidents.

## Failure correction

Common failure modes: AI risk management is limited to data privacy and ignores other AI-specific risks (corrective: expand the scope to include the AI-specific risk sources the standard identifies); risks are identified but not linked to life-cycle stages (corrective: tag each risk with the stages it affects and the controls that mitigate it); post-deployment monitoring is missing or ad hoc (corrective: define monitoring metrics and incident thresholds before deployment); risk register is updated at design only and not after deployment (corrective: schedule periodic risk reviews and trigger risk re-evaluation on deployment data drift).

## Limitations

ISO/IEC 23894 is a guidance standard; it provides a framework, not a recipe. It does not prescribe specific AI risk metrics, fairness tests, or robustness evaluations; those depend on the AI system's context. The standard does not override sector regulations that may mandate specific AI controls. The risk treatment strategies are conceptual; the technical implementation of each treatment is governed by other standards (security, privacy, safety).

## Scope note

This article summarizes project-neutral engineering use of ISO/IEC 23894:2023. It does not assert any specific project's AI risk management outcome or claim any AI safety certification.

## Canonical sources

- ISO/IEC 23894:2023 — Information technology — Artificial intelligence — Guidance on risk management: https://www.iso.org/standard/77304.html