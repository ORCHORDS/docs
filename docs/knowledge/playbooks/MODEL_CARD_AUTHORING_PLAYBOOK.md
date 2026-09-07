# Model Card Authoring Playbook

## Purpose
Provide a repeatable procedure for authoring, reviewing, and
maintaining model cards so that AI/ML models ship with
documentation that supports governance, evaluation, and safe
operational use.

## Audience
Model owners and ML engineers authoring cards, AI governance
reviewers approving them, and reliability engineers consuming
them during deployment and incident response.

## Pre-conditions
- Model version pinned and reproducible per the AI Model Lifecycle
  Playbook.
- Evaluation results available for the agreed evaluation suite.
- Training data sources and known limitations documented by the
  model owner.
- AI risk tier assigned per the AI Risk Tiering Practice Governance
  standard.
- Provenance manifest infrastructure available per the AI Content
  Provenance Governance standard.

## Procedure
1. Author the model card using the agreed template and capture
   model name, version, intended use, out-of-scope use, training
   data summary, and known limitations.
2. Record the evaluation suite, datasets, metrics, and observed
   results including any failure modes identified during
   evaluation.
3. Document the AI risk tier and the rationale for the tier
   assignment, with links to the AI governance review record.
4. Capture operational characteristics (latency, throughput, GPU
   memory, autoscaling behaviour) for the deployment target.
5. Document ethical considerations including fairness evaluation,
   privacy posture, and any known vulnerable populations.
6. Sign the model card using the platform signing identity so the
   card itself is a verifiable artefact.
7. Submit the card for AI governance review and capture the
   approval record before promoting the model to production.
8. Store the signed card in the model registry alongside the
   model artefacts and link it from the deployment manifest.

## Rollback
- Mark the affected card version as deprecated in the model
  registry and prevent further deployments referencing it.
- Replace the card with a corrected version that captures the
  findings from the rollback review.
- Notify dependent services and consumers of the deprecated card
  so they can update their documentation and incident runbooks.
- Capture the failure mode in the post-incident review and update
  this playbook with any newly identified guardrails.

## References
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [AI Content Provenance Governance](../standards/AI_CONTENT_PROVENANCE_GOVERNANCE.md)
- [AI Model Lifecycle Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
- [AI Model Drift Detection Playbook](AI_MODEL_DRIFT_DETECTION.md)
- [MLflow version governance](../reference/MLFLOW_VERSION_GOVERNANCE.md)
