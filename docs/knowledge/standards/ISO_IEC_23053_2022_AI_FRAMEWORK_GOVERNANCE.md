---
title: ISO/IEC 23053:2022 AI Framework Using ML Technologies Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 23053:2022 (first edition, 2022-06) — "Information technology — Artificial intelligence — Artificial intelligence concepts and terminology"; https://www.iso.org/standard/74438.html
---

# ISO/IEC 23053:2022 AI Framework Using ML Technologies Governance

## Scope

This card governs how `orchords-docs` evaluates machine-learning components in reference architectures against ISO/IEC 23053:2022. It is the reference input for any KB card that cites an ML pipeline, a model provider, or an inference service.

## Why this card exists

ISO/IEC 23053 defines the conceptual framework, terminology, and reference architecture for AI systems that use machine-learning technologies. Without a card binding to 23053, the KB cites ML systems with inconsistent terminology and without enumerating the AI lifecycle stages.

## Document structure (Clauses 5 — 9)

| Clause | Title | Project interpretation |
|---|---|---|
| 5 | AI system overview | every reference card that cites an AI system must use the 23053 vocabulary |
| 6 | AI system stakeholder roles | RACI across data engineer, ML engineer, model owner, validator, end user |
| 7 | AI system lifecycle | data acquisition, model development, model deployment, model operation, model retirement |
| 8 | AI system functional view | inference pipeline + monitoring pipeline |
| 9 | AI system non-functional view | performance, robustness, explainability, fairness |

References: `https://www.iso.org/standard/74438.html`.

## Stakeholder roles (Clause 6)

| Role | Responsibility |
|---|---|
| AI customer | consumes the AI system output |
| AI user | invokes the AI system |
| AI operator | maintains the AI system in production |
| AI developer | trains and validates the model |
| AI data engineer | curates the training and evaluation data |
| AI system owner | accountable for the AI system's behavior |
| AI auditor | independent review of the AI system |

## AI system lifecycle (Clause 7)

The five-stage lifecycle:

1. **Data acquisition** — collect, label, validate data.
2. **Model development** — feature engineering, training, hyperparameter tuning.
3. **Model deployment** — package, serve, monitor the model.
4. **Model operation** — observe, evaluate, retrain.
5. **Model retirement** — sunset the model with rollback to the prior version.

Every reference card that cites an AI system must declare which stages are in scope.

## Functional view (Clause 8)

The functional view decomposes into:

- **Inference pipeline** — input preprocessing, model inference, output postprocessing.
- **Monitoring pipeline** — drift detection, fairness monitoring, performance monitoring.
- **Audit pipeline** — explainability trace, decision log, retraining trigger.

## Non-functional view (Clause 9)

| Non-functional | Metric | Project target |
|---|---|---|
| Performance | inference latency p99 | ≤ 200ms for interactive, ≤ 5s for batch |
| Throughput | inferences/second | depends on workload; documented in card |
| Robustness | accuracy under adversarial input | documented per model family |
| Explainability | method available | SHAP, LIME, or attention maps |
| Fairness | demographic parity gap | documented per model family |
| Reproducibility | seed-based reproducibility | ≥ 99% (floating-point non-determinism bounded) |
| Security | adversarial robustness | documented per model family |

## Terminology binding

The KB uses 23053 terminology consistently:

- **AI system** — the overall system including data, model, infrastructure, and operators.
- **ML system** — the AI system subset that uses machine learning.
- **Model** ��� the trained artifact (weights, architecture, hyperparameters).
- **Inference** — the act of using the model to produce an output.
- **Training** — the act of fitting the model to data.
- **Validation** — the act of evaluating the trained model on held-out data.
- **Test data** — data reserved for final evaluation (not used during training or validation).

## Mandatory pre-flight (before adopting a new ML component)

1. The component uses 23053 terminology.
2. The lifecycle stages in scope are documented.
3. The non-functional targets are documented.
4. The stakeholder RACI is documented.
5. The model version is pinned (semantic version or model hash).
6. The data lineage is documented (training data, validation data, test data).
7. The explainability method is documented.
8. The fairness evaluation is documented.

## Cross-reference

- ISO/IEC 23053 binds to ISO/IEC 42001 (AI Management System) for governance.
- ISO/IEC 23053 binds to ISO/IEC 23094 (AI risk management) for risk.
- ISO/IEC 23053 binds to ISO/IEC 24668 (Process management framework for AI) for process.

## Self-attestation cycle

Every 180 days:

1. Walk every reference card that cites an ML component.
2. Confirm 23053 vocabulary is consistent.
3. Confirm lifecycle stages in scope are documented.
4. Update the next-review date.

## Sources

- ISO/IEC 23053:2022: `https://www.iso.org/standard/74438.html`
- ISO/IEC 42001:2023 (AIMS): `https://www.iso.org/standard/81230.html`
- ISO/IEC 24668 (Process management framework for AI): `https://www.iso.org/standard/79016.html`
- NIST AI RMF 1.0: `https://www.nist.gov/itl/ai-risk-management-framework`
- OECD AI Principles: `https://oecd.ai/en/ai-principles`
