---
title: "AI Model Drift Detection Playbook"
standard: "NIST AI 100-1 AI Risk Management Framework, NIST SP 800-39 Risk Management"
publisher: "NIST"
category: "detection-playbook"
subcategory: "ai-governance"
canonical_url: "https://www.nist.gov/itl/ai-risk-management-framework"
status: "approved"
classification: "public"
audience: "AI engineering, MLOps, model governance"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# AI Model Drift Detection Playbook

## Trigger

A deployed AI/ML model shows signs of input drift (feature distribution shifts), concept drift (relationship between inputs and targets changes), or performance drift (quality metrics deviate from baseline). The trigger can be a metric threshold breach, a stakeholder report, or a scheduled periodic review.

## Scope

The playbook applies to:

- Production ML models, embeddings models, and retrieval indexes.
- Generative AI applications where quality, factuality, or refusal behaviour shifts.
- Decision systems whose outputs feed automated or semi-automated actions.

## Inputs

- Baseline metrics captured at deployment.
- Current production metrics with timestamps.
- Feature and label distributions for the most recent evaluation window.
- Owner acknowledgement and customer-facing impact assessment.

## Steps

1. **Confirm the drift signal.** Compare current metrics against the baseline and the noise band. Distinguish real drift from sampling artefacts or instrumentation changes.
2. **Localise the drift.** Determine whether the drift is concentrated in a slice (geography, customer segment, traffic source, prompt template) or uniform.
3. **Diagnose the cause.** Inspect data quality, upstream feature pipelines, retrieval sources, and prompt or template changes. Cross-reference with deployment events, vendor releases, and incident history.
4. **Contain the impact.** If the drift affects safety, factuality, or regulatory obligations, reduce the agent's autonomy, throttle traffic to the affected path, or roll back to the previous model checkpoint.
5. **Engage the model owner.** Brief the owner on findings, propose a remediation track (retrain, recalibrate, redeploy, prompt update), and capture the decision in the model change log.
6. **Re-evaluate.** Run the validation suite against the candidate fix in staging; require parity or improvement on safety, fairness, and accuracy metrics before promotion.
7. **Update the baseline.** Once the new model is in production, capture a fresh baseline and tune drift thresholds based on the new operating point.

## Escalation

Escalate when:

- Drift affects a regulated use case (employment, credit, healthcare).
- Drift correlates with a customer-impacting incident.
- The cause is upstream data poisoning rather than benign distribution shift.

Notify the model owner, the AI risk committee, and the customer success lead.

## Evidence

- Baseline vs current metric comparison with timestamps.
- Slice-level analysis showing where drift is concentrated.
- Root cause hypothesis and supporting telemetry.
- Change ticket and approval chain for the remediation.

## Completion Criteria

The review closes when:

- The drift's cause is documented or a follow-up investigation is opened with an owner.
- A remediation decision (retain, retrain, recalibrate, rollback) is recorded and applied.
- The baseline is updated and the drift detector thresholds are re-tuned.
- The model owner attests to the new operating point.

## Exceptions

- **Vendor-managed model.** Where the model is owned by a third party, the playbook tracks vendor-side drift signals; remediation is coordinated through the vendor's change management.
- **Acceptable drift.** When the model owner accepts the new operating point with documented risk acceptance, the playbook records the acceptance and skips remediation.

## Related Documents

- NIST AI 100-1 AI Risk Management Framework
- NIST SP 800-39 Risk Management
- Model Card and Datasheet documentation conventions
- Agent Model Change Control NIST AI RMF
- AI Model Card Review
