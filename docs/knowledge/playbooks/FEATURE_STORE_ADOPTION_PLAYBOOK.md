# Feature Store Adoption Playbook

## Purpose

Adopt a feature store (Feast, Tecton, Hopsworks Feature Store, or managed equivalent) for a new machine-learning workload that requires online / offline parity, point-in-time correctness, and freshness SLAs. The playbook aligns with [Feature Store Architecture Governance](../standards/FEATURE_STORE_ARCHITECTURE_GOVERNANCE.md), [Feature Pipeline Lineage Governance](../standards/FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md), and [Feature Store Access Control Governance](../standards/FEATURE_STORE_ACCESS_CONTROL_GOVERNANCE.md).

## Audience

Workload owners, ML platform engineers, data engineers, security reviewers.

## Pre-conditions

1. The feature store reference card is current (`FEAST_VERSION_GOVERNANCE.md`, `TECTON_VERSION_GOVERNANCE.md`, `HOPSWORKS_FEATURE_STORE_VERSION_GOVERNANCE.md`).
2. AI Impact Assessment is filed for the workload; see [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md).
3. Tenant scoping and data-classification decisions are documented.
4. Source datasets are registered in the catalogue with documented freshness and retention.
5. A representative training dataset and a representative online-traffic sample are available.

## Procedure

1. **Select the feature store.** Choose Feast for pluggable open-source deployments; choose Tecton for managed freshness contracts and an enterprise SLA; choose Hopsworks Feature Store when a unified data and AI platform is required.
2. **Provision the cluster.** Apply the platform Helm chart or Terraform module pinned to the supported minor; record the cluster manifest in the inventory.
3. **Configure authentication and authorization.** Provision workload-scoped service-account credentials in the central secret manager; enable OIDC for interactive users; disable legacy username/password authentication.
4. **Register online and offline stores.** Select the online and offline backends per the compatibility matrix; record the choice in the feature-store manifest.
5. **Author the feature views.** Declare each view's name, version, entities, source data, transformation, freshness SLA, owner, and AI risk tier. Register transformations in the Feature Platform registry.
6. **Wire lineage.** Emit lineage records with every materialisation and every online write; reject feature values without a complete lineage record.
7. **Backfill historical values.** Run the materialisation job over the representative training window; validate point-in-time correctness.
8. **Validate online / offline parity.** Run the daily parity job over at least 100 sample keys per view; resolve parity regressions before promotion.
9. **Wire observability.** Enable Prometheus metrics, OTLP traces, freshness SLO dashboards, and parity alerts following the standard observability requirements.
10. **Run a security review.** Walk through the [Feature Store Access Control Governance](../standards/FEATURE_STORE_ACCESS_CONTROL_GOVERNANCE.md) threat model; document mitigations and residual risk; file waivers for any unmet controls.
11. **Pilot in staging.** Route 5% of production traffic to the staging cluster; compare freshness, latency, and parity metrics with the baseline.
12. **Promote to production.** Enable the production cluster; set the freshness SLA alert and the parity alert; hand off to the on-call rotation.
13. **Adopt the operating cadence.** Schedule the quarterly parity regression, the annual threat-model review, and the 180-day standard review.

## Rollback

1. Stop the materialisation pipeline and freeze new feature writes.
2. Switch the workload back to the previous feature source (direct database access, prior feature store, or pre-computed table).
3. Quarantine the affected feature views for forensic review; do not delete until the security review is complete.
4. Open a remediation ticket that captures the parity regression, the freshness breach, or the security finding.
5. Communicate the rollback to stakeholders via the standard incident communication channel.
6. Update the workload specification with the lessons learned before the next adoption attempt.

## References

- [Feature Store Architecture Governance](../standards/FEATURE_STORE_ARCHITECTURE_GOVERNANCE.md)
- [Feature Pipeline Lineage Governance](../standards/FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md)
- [Feature Store Access Control Governance](../standards/FEATURE_STORE_ACCESS_CONTROL_GOVERNANCE.md)
- [Feast Open Source Feature Store Version Governance](../reference/FEAST_VERSION_GOVERNANCE.md)
- [Tecton Feature Platform Version Governance](../reference/TECTON_VERSION_GOVERNANCE.md)
- [Hopsworks Feature Store Version Governance](../reference/HOPSWORKS_FEATURE_STORE_VERSION_GOVERNANCE.md)
- [MLflow Model Registry Version Governance](../reference/MLFLOW_VERSION_GOVERNANCE.md)
- [KServe Model Serving Version Governance](../reference/KSERVE_VERSION_GOVERNANCE.md)
- [Triton Inference Server Version Governance](../reference/TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
