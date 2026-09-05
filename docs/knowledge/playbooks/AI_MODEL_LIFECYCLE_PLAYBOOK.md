# AI Model Lifecycle Management Playbook

## Purpose

Govern the end-to-end AI model lifecycle: training data curation, model development, model deployment, model operation, and model retirement. The playbook aligns with ISO/IEC 23053 (AI framework), ISO/IEC 42001 (AIMS), ISO/IEC 27402 (AI security), and NIST AI RMF.

## Audience

AI platform engineers, ML engineers, AI auditors, model owners.

## Pre-conditions

1. The reference card for the protocol is current (`ISO_IEC_23053_2022_AI_FRAMEWORK_GOVERNANCE.md`, `ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md`, `ISO_IEC_42001_2023_AIMS_GOVERNANCE.md`).
2. AI Impact Assessment is filed for the new model.
3. Stakeholder RACI is documented.
4. Model artifact versioning policy is in place.
5. Observability stack is wired for the inference service.

## Procedure

### 1. Data acquisition

1. Document the data sources: provenance, license, lawful basis, retention.
2. Validate the data: distribution, missingness, class imbalance, label noise.
3. Apply PII controls: pseudonymization, minimization, consent recording.
4. Version the dataset (DVC, lakeFS, or equivalent).
5. Compute dataset-level statistics: feature histograms, label distribution, demographic distribution.

### 2. Model development

1. Document the model architecture, hyperparameters, and training recipe.
2. Pin the training environment (Python version, framework version, GPU/CPU type).
3. Pin the random seed for reproducibility.
4. Track every experiment (MLflow, Weights & Biases, or equivalent).
5. Compute validation metrics: accuracy, calibration, fairness across demographic groups.
6. Adversarial evaluation per ISO/IEC 27402 A.7.3.
7. Explainability evaluation per ISO/IEC 27402 A.7.11.
8. Document the model card (model type, intended use, out-of-scope use, training data, evaluation data, metrics, fairness, explainability).

### 3. Model deployment

1. Sign the model artifact (cosign, GPG, or equivalent).
2. Publish the model card to a model registry (MLflow, Weights & Biases, BentoML).
3. Pin the model version in the inference service configuration.
4. Run integration tests against the inference service.
5. Run shadow-mode inference: serve the new model alongside the old for a defined window.
6. Validate shadow-mode output against the old model: divergence rate, latency, error rate.
7. Cut over: route production traffic to the new model.

### 4. Model operation

1. Observe drift: feature drift, label drift, prediction drift, concept drift.
2. Observe performance: latency p99, error rate, throughput.
3. Observe fairness: demographic parity gap, equalized odds.
4. Observe security: prompt injection rate (LLMs), jailbreak rate, adversarial input rate.
5. Re-evaluate on a scheduled cadence (weekly for high-stakes models, monthly otherwise).
6. Trigger retraining when drift exceeds threshold.
7. Maintain the decision log: every inference logged with input, output, model version, timestamp.
8. Maintain the explainability trace for every high-stakes inference.

### 5. Model retirement

1. Notify consumers of the deprecation window (≥ 90 days).
2. Route traffic to the replacement model.
3. Stop the inference service.
4. Archive the model artifact and the model card.
5. Redact PII from the decision log (if required by retention policy).
6. Document the retirement in the model registry.

### 6. Observability

- `model.inference.latency_ms` (histogram)
- `model.inference.error.count` (counter, by error type)
- `model.drift.feature_ks_distance` (gauge, per feature)
- `model.drift.prediction_kl_divergence` (gauge)
- `model.fairness.demographic_parity_gap` (gauge, per group)
- `model.security.prompt_injection.count` (counter)
- `model.security.jailbreak.count` (counter)
- `model.explainability.coverage` (gauge)

### 7. Incident response

1. Detect: anomaly in drift, fairness, security, or performance metrics.
2. Contain: route traffic to the last-known-good model; alert the on-call.
3. Investigate: review the decision log, retraining history, data lineage.
4. Remediate: retrain, rollback, or accept (with documented justification).
5. Document: `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## Rollback

Rollback decisions:

- p99 inference latency > 2x baseline → revert to last-known-good model.
- Error rate > 5% for 5 minutes → revert.
- Fairness regression > 5% absolute → revert.
- Security incident (prompt injection, jailbreak, data leak) → revert.

Rollback procedure:

1. Revert the inference service to the last-known-good model version.
2. Validate behavior in production.
3. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `ISO_IEC_23053_2022_AI_FRAMEWORK_GOVERNANCE.md`
- `ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md`
- `ISO_IEC_42001_2023_AIMS_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- NIST AI RMF: `https://www.nist.gov/itl/ai-risk-management-framework`
- OWASP LLM Top 10: `https://owasp.org/www-project-top-10-for-large-language-model-applications/`
- MITRE ATLAS: `https://atlas.mitre.org/`
