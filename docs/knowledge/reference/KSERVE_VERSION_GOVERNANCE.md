---
title: KServe Model Serving Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/kserve/kserve
---

# KServe Model Serving Version Governance

## Purpose
Define how teams select, upgrade, and operate KServe inference
service deployments so machine learning models can be served at scale
with predictable latency, autoscaling, and traffic management
behaviour.

## Scope
Applies to KServe InferenceService, the KServe controller, and
supporting components (Knative, Istio or compatible ingress,
supported storage backends) deployed across development, staging,
and production Kubernetes clusters.

## Version Line Policy
- Track the latest stable minor release for at least 90 days before
  declaring it production-ready.
- Hold one previous minor release available for rollback for at least
  30 days after promotion.
- Skip releases with breaking changes to the InferenceService CRD,
  predictor schema, or transformer contract without an internal
  exception record.
- Align KServe controller version with the Knative Serving and
  Istio versions deployed in the cluster.

## Component Lifecycle
- Predictor frameworks (Triton, TensorFlow Serving, TorchServe,
  vLLM, ONNX Runtime) progress through the upstream maturity ladder
  per their own governance cards.
- Transformer, explainer, and pre/post-processing components MUST be
  re-validated per upgrade for schema and runtime compatibility.
- InferenceService CRD versions evolve per release and require
  coordinated conversion webhook updates.

## Compatibility Considerations
- Underlying Knative Serving and Istio versions MUST be on releases
  supported by the chosen KServe release.
- Storage backends (S3-compatible object stores, GCS, Azure Blob,
  PVC) MUST be configured with the credentials expected by KServe's
  storage initializer.
- Authentication, authorisation, and traffic splitting MUST
  interoperate with the platform identity provider and ingress
  layer.
- Autoscaling behaviour (HPA, KEDA, Knative scale metrics) MUST be
  consistent with the platform's observability and alerting
  standards.

## Upgrade Procedure
1. Read upstream release notes and identify breaking changes affecting
   InferenceService CRD, predictor schema, or transformer contract.
2. Validate the new release in a staging cluster with a snapshot of
   representative InferenceService definitions and traffic patterns.
3. Run a canary upgrade for a single namespace and confirm
   prediction, autoscaling, and traffic split behaviour matches
   expectations under synthetic load.
4. Promote the upgrade across remaining namespaces with pre-staged
   rollback artefacts and on-call coverage.
5. Record the upgrade window, observed deltas, and any compensating
   configuration changes in the change log.

## Rollback Procedure
- Re-deploy the previous KServe controller and webhook configuration
  from the versioned artefact store.
- Restore the prior InferenceService CRD definitions so existing
  services match the pre-upgrade contract.
- Re-validate prediction, autoscaling, and traffic split behaviour
  against the synthetic probes.
- Open a regression ticket capturing the cause of the rollback and
  link it to the originating upgrade record.

## Security Considerations
- Pin KServe controller and webhook images by digest and verify
  signatures using the container trust store.
- Restrict InferenceService mutation access to authorised operators
  and CI promotion pipelines.
- Use external identity providers for ingress-level authentication
  and disable local admin accounts outside break-glass scenarios.
- Scrub sensitive payloads before logging at the transformer layer
  and enforce request-size limits at the ingress layer.

## Operational Impact Points
- Controller upgrades require webhook reconfiguration; expect
  momentary prediction delays covered by pod autoscaling.
- Cold-start latency and GPU allocation behaviour vary by predictor
  framework and MUST be baselined before promotion.
- Traffic split and canary rollout patterns MUST be aligned with the
  model lifecycle playbook.
- Storage credential rotation MUST be coordinated with KServe's
  storage initializer refresh schedule.

## Cross-References
- See [MLflow version governance](MLFLOW_VERSION_GOVERNANCE.md) for
  upstream model registry integration.
- See [Triton Inference Server version governance](TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md)
  for runtime compatibility.
- See [AI Model Lifecycle Playbook](../playbooks/AI_MODEL_LIFECYCLE_PLAYBOOK.md)
  for end-to-end lifecycle practice.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
