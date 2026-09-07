---
title: Prefect Workflow Orchestrator Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/PrefectHQ/prefect/releases
---

# Prefect Workflow Orchestrator Version Governance

## Why this card exists

Prefect is the dynamic, Python-native orchestrator used by OrchestrAI products that require dynamic DAGs, lightweight serverless execution, and a managed control plane (Prefect Cloud). Prefect releases combine a Python SDK, an API server, and worker processes on independent cadences. Each major version ships breaking changes in the flow / task API, the work-pool contract, and the storage schema. This card defines how OrchestrAI selects, upgrades, and retires Prefect versions across Prefect Open Source and Prefect Cloud.

## Scope

Applies to Prefect deployments (Prefect Open Source, Prefect Cloud, the Python SDK embedded in pipelines, and Prefect workers). Excludes the underlying compute engines (Kubernetes, ECS, Databricks) which are governed by their own cards.

## Versioning model

Prefect follows `<major>.<minor>.<patch>`:

- **Major** — incompatible flow / task API, breaking work-pool contract, or removal of a supported storage backend.
- **Minor** — backward-compatible feature additions (new work-pool types, new storage backends, new task runners); flow contract is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 3.2.x | Primary | 2027-03 | Default for new deployments; introduces the work-pool v3 contract and the deployments v4 schema. |
| 3.1.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 3.0.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 3.0 | End of life | — | Not permitted in production; assessed as a finding by the internal audit. |

## Selection criteria

1. New deployments default to the latest stable minor in the 3.2.x line.
2. The pin is recorded in the orchestrator manifest and validated by the platform reconciliation loop.
3. Pre-release builds are restricted to evaluation deployments and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version flow-parity regression suite and the work-pool migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises flow export / import, work-pool schema upgrade, and worker reconnect.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Deployments on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new deployments cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| `prefect` Python SDK | 3.1.x, 3.2.x | SDK minor must match API server minor. |
| API server | matches SDK minor | Prefect Cloud hosted by vendor; on-prem deployable via Docker / Helm. |
| Worker / agent | matches SDK minor | Replaced the legacy agent model from 3.0+. |
| PostgreSQL | 14, 15, 16, 17 | Required for on-prem API server; see [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md). |
| Work pools | Kubernetes, ECS, Databricks, Docker, Process, Serverless | Selection recorded in the orchestrator manifest. |
| Storage | S3, GCS, Azure Blob, local | Required for flow result persistence. |

## Security and compliance

- TLS is mandatory for all SDK, API server, and worker traffic.
- Work-pool access is gated by RBAC; legacy single-workspace access is deprecated.
- Audit logging is wired through the standard log pipeline; flow-run-level audit events must include `flow_name`, `work_pool`, `actor`, `operation`, and `flow_run_id`.
- Personal data flowing through Prefect flows is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the API server metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Flow-run traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for work-pool saturation, late-run rate, and worker error rate live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Dagster Data Orchestrator Version Governance](DAGSTER_VERSION_GOVERNANCE.md)
- [Apache Airflow Workflow Orchestrator Version Governance](AIRFLOW_VERSION_GOVERNANCE.md)
- [Temporal Durable Execution Version Governance](TEMPORAL_VERSION_GOVERNANCE.md)
- [Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance](ARGO_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
