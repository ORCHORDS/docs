---
title: Dagster Data Orchestrator Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/dagster-io/dagster/releases
---

# Dagster Data Orchestrator Version Governance

## Why this card exists

Dagster is the asset-centric orchestrator used by OrchestrAI products that require first-class lineage between code, data assets, and compute, with software-defined assets and declarative partitioning. Dagster releases combine a Python SDK, a web UI (Dagit / Dagster Webserver), and a long-running daemon (dagster-daemon) on independent cadences. Each major version ships breaking changes in the asset / op API, the storage schema, and the sensor / schedule model. This card defines how OrchestrAI selects, upgrades, and retires Dagster versions across self-hosted Dagster Open Source, Dagster+, and embedded deployments.

## Scope

Applies to Dagster deployments (Dagster Open Source, Dagster+, the Python SDK embedded in notebooks and pipelines, and Dagster Pipes for external execution). Excludes the underlying compute engines (Kubernetes, Databricks, ECS) which are governed by their own cards.

## Versioning model

Dagster follows `<major>.<minor>.<patch>`:

- **Major** — incompatible asset / op API, breaking storage schema, or removal of a supported executor.
- **Minor** — backward-compatible feature additions (new asset materialisations, new partition types, new executor integrations); storage schema is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 1.9.x | Primary | 2027-03 | Default for new deployments; introduces the asset-graph v3 contract and the new dagster-webserver frontend. |
| 1.8.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 1.7.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 1.7 | End of life | — | Not permitted in production; assessed as a finding by the internal audit. |

## Selection criteria

1. New deployments default to the latest stable minor in the 1.9.x line.
2. The pin is recorded in the orchestrator manifest and validated by the platform reconciliation loop.
3. Pre-release builds (`-rc.N`) are restricted to evaluation deployments and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version asset-parity regression suite and the run-history migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises asset-graph export / import, sensor replay, and storage schema upgrade.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Deployments on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new asset definitions cannot be registered on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| `dagster` Python SDK | 1.8.x, 1.9.x | SDK minor must match webserver / daemon minor. |
| `dagster-webserver` | matches SDK minor | Replaced the legacy `dagit` frontend from 1.7+. |
| `dagster-daemon` | matches SDK minor | Runs sensors, schedules, and run coordinators. |
| PostgreSQL | 14, 15, 16, 17 | Required for run / event log storage; see [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md). |
| Executors | in-process, multiprocess, k8s, celery, docker | Selection recorded in the orchestrator manifest. |
| Compute engines | Databricks, Spark, AWS EMR, ECS, Kubernetes | Selection recorded in the orchestrator manifest. |

## Security and compliance

- TLS is mandatory for all SDK, webserver, and daemon traffic.
- Code-location access is gated by RBAC; legacy single-user code locations are deprecated.
- Audit logging is wired through the standard log pipeline; asset-level audit events must include `asset_key`, `partition_key`, `actor`, `operation`, and `run_id`.
- Personal data flowing through Dagster assets is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the daemon metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Run, asset, and sensor traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for materialisation lag, run failure rate, and sensor backlog live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Prefect Workflow Orchestrator Version Governance](PREFECT_VERSION_GOVERNANCE.md)
- [Apache Airflow Workflow Orchestrator Version Governance](AIRFLOW_VERSION_GOVERNANCE.md)
- [Temporal Durable Execution Version Governance](TEMPORAL_VERSION_GOVERNANCE.md)
- [Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance](ARGO_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
