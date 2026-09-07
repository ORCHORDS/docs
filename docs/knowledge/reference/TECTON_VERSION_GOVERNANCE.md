---
title: Tecton Feature Platform Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://docs.tecton.ai/docs/released-versions
---

# Tecton Feature Platform Version Governance

## Why this card exists

Tecton is the managed feature platform used by OrchestrAI products that require enterprise-grade feature engineering with strong guarantees around freshness SLAs, point-in-time correctness, and managed online + offline serving. Tecton releases cluster versions, SDK versions, and managed-control-plane versions on independent cadences. This card defines how OrchestrAI selects, upgrades, and retires Tecton versions across self-hosted (Tecton on Kubernetes) and Tecton Cloud deployments.

## Scope

Applies to Tecton clusters (self-hosted and managed) and the Tecton SDK (`tecton` Python package, Spark / Databricks integration, and the CLI). Excludes the underlying compute engines (Databricks, EMR, Spark, Snowflake) and online stores (DynamoDB, Aurora, Redis) which are governed by their own cards.

## Versioning model

Tecton follows a layered versioning model:

- **Cluster version** — `<year>.<quarter>.<patch>` aligned to the upstream release cadence; introduces and removes platform features.
- **SDK version** — `<major>.<minor>.<patch>`; must be compatible with the cluster version per the compatibility matrix.
- **CLI version** — pinned per workspace and matched to the SDK major.

A **LTS** designation is applied to a cluster minor and guarantees patch backports for 12 months.

## Supported versions

| Cluster version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 2025.6.x LTS | Primary | 2026-12 | Default for new clusters; introduces the feature-warehouse GA and per-feature freshness contracts. |
| 2025.5.x | Maintenance | 2026-06 | Receives security patches; recommended upgrade path. |
| 2025.4.x | End of life | 2025-12 | Unsupported; migrations must complete before renewal of any compliance certification. |
| < 2025.4 | End of life | — | Not permitted in production. |

| SDK version | Status | Notes |
| --- | --- | --- |
| 1.5.x | Primary | Compatible with cluster 2025.5 and 2025.6. |
| 1.4.x | Maintenance | Compatible with cluster 2025.5 only. |
| < 1.4 | End of life | — |

## Selection criteria

1. New clusters default to the latest LTS cluster minor (currently 2025.6.x).
2. The pin is recorded in the feature-store manifest and validated by the platform reconciliation loop.
3. New workspaces install the latest stable SDK matching the cluster minor.

## Upgrade cadence

- **Cluster patch** — applied within 14 days of upstream release.
- **Cluster minor (LTS)** — applied within 90 days; coordinated with the embedding-model registry when feature transformations depend on a specific model version.
- **Cluster minor (non-LTS)** — applied within 180 days; gated by a staging rehearsal that exercises feature-warehouse migration, online-store schema upgrade, and freshness-contract regression.

## Deprecation process

1. Deprecation is recorded against the cluster inventory on the date upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but lose eligibility for new feature rollouts.
3. The cluster policy controller blocks new feature-view registration on unsupported versions; reads continue until the next maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| `tecton` Python SDK | 1.4.x, 1.5.x | SDK minor must be compatible with cluster minor. |
| Databricks runtime | 13.x, 14.x, 15.x | Required for notebook authoring and materialisation. |
| EMR | 6.15.x, 7.x | Used for materialisation on AWS. |
| Online store | DynamoDB, Aurora MySQL/PostgreSQL, Redis | Selection recorded in the feature-store manifest. |
| Offline store | Snowflake, BigQuery, Redshift, Databricks | Selection recorded in the feature-store manifest. |
| Spark | 3.5.x | Required for batch transformations. |

## Security and compliance

- TLS is mandatory for all SDK, cluster, and registry traffic.
- Service-account credentials are scoped per workspace and rotated at least every 90 days.
- Audit logging is wired through the standard log pipeline; feature-warehouse DDL and DML must include `actor`, `feature_view`, `entity_key`, and `feature_version`.
- Personal data flowing through feature views is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the cluster's monitoring endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Cluster traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for freshness lag, point-in-time correctness, and online-store error rate live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Feast Open Source Feature Store Version Governance](FEAST_VERSION_GOVERNANCE.md)
- [Hopsworks Feature Store Version Governance](HOPSWORKS_FEATURE_STORE_VERSION_GOVERNANCE.md)
- [MLflow Model Registry Version Governance](MLFLOW_VERSION_GOVERNANCE.md)
- [KServe Model Serving Version Governance](KSERVE_VERSION_GOVERNANCE.md)
- [Triton Inference Server Version Governance](TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
