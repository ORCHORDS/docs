---
title: Feast Open Source Feature Store Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/feast-dev/feast/releases
---

# Feast Open Source Feature Store Version Governance

## Why this card exists

Feast is the primary open-source feature store for OrchestrAI products that require on-demand transformation, online + offline parity, and pluggable object-store / online-store backends. Feast's release cadence combines a Python SDK (the `feast` package), a Go-based feature server, and pluggable infrastructure (online stores, offline stores, batch engines). Each major version ships incompatible registry schemas, breaking SDK signatures, and materialisation engine rewrites. This card defines how OrchestrAI selects, upgrades, and retires Feast versions across self-hosted clusters and managed equivalents.

## Scope

Applies to all Feast deployments (open source Feast, Feast on Kubernetes, and the Python SDK embedded in notebooks and pipelines) operated by OrchestrAI. Excludes the underlying online-store and offline-store engines, which are governed by their own version governance cards (Redis, BigQuery, Snowflake, Parquet-on-object-storage, and so on).

## Versioning model

Feast follows `<major>.<minor>.<patch>` semantics with a 0.x pre-1.0 line and a 1.x stable line:

- **Major** — incompatible registry schema, breaking SDK contract, or removal of a supported online / offline store.
- **Minor** — backward-compatible feature additions (new entity types, new transformation engines, new online stores, new materialisation strategies); registry schema is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 0.50.x | Primary | 2027-03 | Default for new deployments; introduces the universal `FeatureView` schema and the ODFV (on-demand feature view) v2 contract. |
| 0.49.x | Maintenance | 2026-09 | Receives security patches only; upgrade recommended. |
| 0.48.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 0.48 | End of life | — | Not permitted in production; assessed as a finding by the internal audit. |

## Selection criteria

1. New deployments default to the latest stable minor in the 0.50.x line.
2. The pin is recorded in the feature-store manifest and validated by the platform reconciliation loop.
3. Pre-release builds (`-rc.N`) are restricted to evaluation clusters and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version feature-parity regression suite and the registry migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises registry export / import, online-store schema upgrade, and offline-store materialisation parity.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Deployments on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new feature views cannot be registered on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| `feast` Python SDK | 0.49.x, 0.50.x | SDK minor must match server minor for materialisation and retrieval parity. |
| `feast-feature-server` (Go) | matches server minor | Deployed as a sidecar; image pinned via Helm. |
| Online stores | Redis 7.x, DynamoDB, Databricks, Bigtable | Selection recorded in the feature-store manifest. |
| Offline stores | BigQuery, Snowflake, Redshift, Parquet-on-S3 | Selection recorded in the feature-store manifest. |
| Batch engine | Spark 3.5.x, Ray 2.30+ | Required for materialisation jobs. |
| Stream engine | Kafka 3.5.x, 3.6.x, Kinesis | Used for stream features. |

## Security and compliance

- TLS is mandatory for all SDK, feature-server, and registry traffic.
- Registry access is gated by RBAC; legacy single-user registry authentication is deprecated.
- Audit logging is wired through the standard log pipeline; feature-view-level audit events must include `feature_view`, `entity_key`, `actor`, `operation`, and `feature_version`.
- Personal data flowing through feature views is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on `:6566/metrics`; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Materialisation and retrieval traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for materialisation lag, freshness SLA, and online-store error rate live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Tecton Feature Platform Version Governance](TECTON_VERSION_GOVERNANCE.md)
- [Hopsworks Feature Store Version Governance](HOPSWORKS_FEATURE_STORE_VERSION_GOVERNANCE.md)
- [MLflow Model Registry Version Governance](MLFLOW_VERSION_GOVERNANCE.md)
- [KServe Model Serving Version Governance](KSERVE_VERSION_GOVERNANCE.md)
- [Triton Inference Server Version Governance](TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-218A GenAI Profile Version Governance](../standards/NIST_SP_800_218A_GENAI_PROFILE_VERSION_GOVERNANCE.md)
