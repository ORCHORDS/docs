---
title: Hopsworks Feature Store Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/logicalclocks/hopsworks/releases
---

# Hopsworks Feature Store Version Governance

## Why this card exists

Hopsworks is the unified data and AI platform used by OrchestrAI products that require a tightly integrated feature store, model registry, and notebook environment on a single cluster. Hopsworks' feature store combines a Python SDK, a Java backend, an online store (RonDB / MySQL Cluster), and an offline store (Hudi on object storage). Major versions ship breaking changes in the feature-group API, the online-store schema, and the authentication model. This card defines how OrchestrAI selects, upgrades, and retires Hopsworks versions across self-hosted clusters and Hopsworks Cloud.

## Scope

Applies to Hopsworks clusters (self-hosted and managed) and the Hopsworks Feature Store Python SDK (`hsfs`). Excludes the underlying storage engines (Hudi, RonDB) which are governed by their own cards.

## Versioning model

Hopsworks follows `<major>.<minor>.<patch>`:

- **Major** — incompatible feature-group API, breaking authentication model, or removal of a supported online store.
- **Minor** — backward-compatible feature additions (new feature-group types, new transformation engines, new online-store backends); feature-group schema is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 4.2.x | Primary | 2027-02 | Default for new clusters; introduces the feature-group v3 contract and the managed-vector online store. |
| 4.1.x | Maintenance | 2026-08 | Receives security patches; recommended upgrade path. |
| 4.0.x | End of life | 2026-02 | Unsupported; migration required before compliance renewal. |
| < 4.0 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest stable minor in the 4.2.x line.
2. The pin is recorded in the cluster manifest and validated by the platform reconciliation loop.
3. Pre-release builds are restricted to evaluation clusters and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the feature-group parity regression suite and the online-store schema migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises feature-group export / import, online-store upgrade, and authentication model migration.

## Deprecation process

1. Deprecation is recorded against the cluster inventory on the date upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but lose eligibility for new feature rollouts.
3. The cluster policy controller blocks new feature-group creation on unsupported versions; reads continue until the next maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| `hsfs` Python SDK | 4.1.x, 4.2.x | SDK minor must match cluster minor. |
| Online store | RonDB 21.x, MySQL Cluster 8.x | Selection recorded in the cluster manifest. |
| Offline store | Hudi 0.14.x, 0.15.x | Required for offline feature groups. |
| Object storage | S3, GCS, ADLS, MinIO | Required for Hudi tables. |
| Spark | 3.5.x | Required for batch transformations. |
| Kafka | 3.5.x, 3.6.x | Required for stream feature pipelines. |

## Security and compliance

- TLS is mandatory for all SDK, API, and inter-node traffic.
- OIDC-based authentication is required; legacy username/password authentication is deprecated.
- Audit logging is wired through the standard log pipeline; feature-group-level audit events must include `feature_group`, `feature_view`, `entity_key`, `actor`, and `feature_version`.
- Personal data flowing through feature groups is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the cluster's monitoring endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Cluster traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for materialisation lag, online-store latency, and feature-freshness SLA live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Feast Open Source Feature Store Version Governance](FEAST_VERSION_GOVERNANCE.md)
- [Tecton Feature Platform Version Governance](TECTON_VERSION_GOVERNANCE.md)
- [MLflow Model Registry Version Governance](MLFLOW_VERSION_GOVERNANCE.md)
- [KServe Model Serving Version Governance](KSERVE_VERSION_GOVERNANCE.md)
- [Triton Inference Server Version Governance](TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
