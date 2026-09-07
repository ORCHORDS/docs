# Feature Store Architecture Governance

## 1. Scope

Govern the architecture, selection, and operational use of feature stores (Feast, Tecton, Hopsworks Feature Store, and managed equivalents) across OrchestrAI products. Covers online / offline parity, point-in-time correctness, freshness SLAs, and integration with model serving.

Excludes the underlying online / offline storage engines, which are governed by their own cards (Redis, BigQuery, Snowflake, Hudi, RonDB). Excludes embedding pipelines, which are governed by [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md).

## 2. Normative references

- [Feast Open Source Feature Store Version Governance](../reference/FEAST_VERSION_GOVERNANCE.md)
- [Tecton Feature Platform Version Governance](../reference/TECTON_VERSION_GOVERNANCE.md)
- [Hopsworks Feature Store Version Governance](../reference/HOPSWORKS_FEATURE_STORE_VERSION_GOVERNANCE.md)
- [MLflow Model Registry Version Governance](../reference/MLFLOW_VERSION_GOVERNANCE.md)
- [KServe Model Serving Version Governance](../reference/KSERVE_VERSION_GOVERNANCE.md)
- [Triton Inference Server Version Governance](../reference/TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)

## 3. Terms and definitions

- **Feature view** — a versioned, named definition of how a feature is computed, including its entities, source data, transformation, and freshness SLA.
- **Online store** — a low-latency key-value store that serves feature values to online inference.
- **Offline store** — a columnar analytical store that holds historical feature values for training and backfill.
- **Point-in-time correctness** — the property that training-time feature joins do not leak future information relative to the label.
- **Freshness SLA** — the maximum delay between a feature value being produced in the source system and that value being available for online inference.

## 4. Feature store selection

1. Feast is the default open-source feature store for new OrchestrAI deployments that need pluggable online / offline backends and a permissive license.
2. Tecton is preferred for regulated or high-freshness workloads that require managed freshness contracts and an enterprise SLA.
3. Hopsworks Feature Store is preferred when the workload needs a unified data and AI platform on a single cluster.
4. The choice is recorded in the feature-store manifest and reviewed annually.

## 5. Feature view contract

1. Every feature view declares its name, version, entities, source data, transformation, online-store backend, offline-store backend, freshness SLA, owner, and AI risk tier.
2. Feature view versions are immutable; breaking changes require a new major version.
3. Backwards-compatible additions (new features, new transformation parameters) are permitted under a new minor version.
4. Deprecated feature views remain readable for at least 180 days after deprecation; the deprecation date and the migration target are recorded in the manifest.

## 6. Online / offline parity

1. The same feature-view definition must produce values that match between the online store and the offline store, modulo freshness window.
2. Parity is validated by a daily job that samples at least 100 feature keys per view and compares values within the declared tolerance.
3. Parity failures above 1% open a remediation ticket and block promotion of any new model that consumes the affected view.
4. Parity validation is wired to the alerting pipeline; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).

## 7. Point-in-time correctness

1. Training data joins must use the feature view's point-in-time join API; ad-hoc joins in notebooks are prohibited for production datasets.
2. Point-in-time joins are validated against a synthetic test set at least every 90 days.
3. New feature views must declare their point-in-time semantics (`event_time`, `created_time`, `ttl`) in the feature view contract.

## 8. Freshness SLA

1. Every online feature view declares a freshness SLA in seconds; the SLA is enforced by the platform.
2. Freshness breaches are alerted to the workload owner; chronic breaches trigger a freshness-contract review.
3. Materialisation jobs run on a schedule; ad-hoc materialisation is permitted only with a documented change ticket.

## 9. Integration with model serving

1. Feature retrieval from the online store must complete within the model-serving latency budget; see [KServe Model Serving Version Governance](../reference/KSERVE_VERSION_GOVERNANCE.md) and [Triton Inference Server Version Governance](../reference/TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md).
2. Feature values are propagated to the model-serving tier via the standard retrieval API; direct database access from the serving tier is prohibited.
3. The model registry ([MLflow Model Registry Version Governance](../reference/MLFLOW_VERSION_GOVERNANCE.md)) records the feature-view versions consumed by each model version.

## 10. Security

1. TLS is required for all SDK, API, and inter-node traffic.
2. Access to feature views is gated by RBAC; legacy single-user access is deprecated.
3. Personal data in feature views is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Vector embeddings derived from feature views are governed by [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md).

## 11. Operating model

1. The Feature Platform team owns the shared feature-store infrastructure and the reference feature-view templates.
2. Workload owners own their feature views, freshness SLAs, and parity validation.
3. The Feature Platform guild meets monthly to review parity regressions, capacity, and adoption of new feature stores.
4. New feature-store vendors are evaluated by the Feature Platform team and approved by the AI Governance Council.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
