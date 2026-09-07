# Inference Platform Rollout Playbook

## Purpose
Provide a repeatable procedure for rolling out a new inference
platform (KServe, Triton, or compatible serving stack) so that
machine learning models can be served with predictable performance,
autoscaling, and observability characteristics across the platform.

## Audience
Platform engineers deploying inference infrastructure, ML
engineers migrating models to the new platform, and reliability
engineers integrating the platform with incident response.

## Pre-conditions
- Inference platform version pinned and approved per the relevant
  version governance cards.
- Model registry integrated with the inference platform storage
  backend and credentials provisioned through the secret manager.
- Autoscaling policy, request limits, and timeouts agreed with
  service owners.
- Observability instrumentation aligned with the platform
  Prometheus and OpenTelemetry standards.
- Rollback artefacts pre-staged in the artefact store.

## Procedure
1. Confirm the rollout plan covers model migration order, traffic
   shift schedule, and rollback decision criteria.
2. Deploy the inference platform to the staging cluster and
   validate end-to-end prediction, autoscaling, and observability
   against synthetic traffic.
3. Migrate a pilot model end-to-end (registry → serving → monitor)
   and run the agreed evaluation suite to confirm parity with the
   prior serving platform.
4. Shift a small percentage of production traffic to the new
   platform and compare latency, throughput, and error rates
   against the previous baseline.
5. Promote the rollout through traffic waves with pre-defined
   rollback decision criteria and on-call coverage.
6. Update service runbooks, dashboards, and alert routing to
   reference the new platform endpoints.
7. Decommission the prior platform only after the migration is
   complete and audit evidence is captured.

## Rollback
- Shift traffic back to the previous platform via the platform
  gateway and confirm parity against the pre-rollout baseline.
- Pause model promotion through the inference platform registry so
  no further models are migrated until the rollback review
  completes.
- Re-enable the previous platform's observability dashboards and
  alerts if they were suspended during the rollout.
- Capture the failure mode in the post-incident review and update
  this playbook with any newly identified guardrails.

## References
- [KServe version governance](../reference/KSERVE_VERSION_GOVERNANCE.md)
- [Triton Inference Server version governance](../reference/TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md)
- [MLflow version governance](../reference/MLFLOW_VERSION_GOVERNANCE.md)
- [AI Model Lifecycle Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
- [Model Card Authoring Playbook](MODEL_CARD_AUTHORING_PLAYBOOK.md)
