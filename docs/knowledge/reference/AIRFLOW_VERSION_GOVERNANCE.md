---
title: Apache Airflow Workflow Orchestrator Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://airflow.apache.org/docs/apache-airflow/stable/release_notes.html
---

# Apache Airflow Workflow Orchestrator Version Governance

## Why this card exists

Apache Airflow is the most widely deployed workflow orchestrator and is used by OrchestrAI products that require mature provider ecosystem, broad executor coverage, and a stable DAG-as-code model. Airflow releases combine a Python SDK, a webserver, a scheduler, and an executor on independent cadences. Each major version ships breaking changes in the DAG serialisation model, the executor contract, and the metadata database schema. This card defines how OrchestrAI selects, upgrades, and retires Airflow versions across self-hosted deployments, the Astronomer distribution, and managed equivalents (MWAA, Cloud Composer).

## Scope

Applies to Apache Airflow deployments (Apache Airflow Open Source, Astronomer, Amazon MWAA, Google Cloud Composer) and the Airflow Python SDK embedded in pipelines. Excludes the underlying compute engines (Kubernetes, Celery, Databricks) which are governed by their own cards.

## Versioning model

Airflow follows `<major>.<minor>.<patch>`:

- **Major** — incompatible DAG / task API, breaking metadata-database schema, or removal of a supported executor.
- **Minor** — backward-compatible feature additions (new operators, new hooks, new executor integrations); metadata-database schema is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

Long-Term-Support releases are labelled `.<minor>.LTS` (e.g. `2.11.0-LTS`) and receive patch backports for 18 months per the Airflow PMC.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 3.0.x | Primary | 2026-12 | Default for new deployments; introduces the DAG v3 contract, the Airflow 3 UI, and the task execution API. |
| 2.11.x LTS | Maintenance | 2027-04 | Receives security patches; recommended for workloads that depend on classic operators. |
| 2.10.x | End of life | 2026-04 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 2.10 | End of life | — | Not permitted in production. |

## Selection criteria

1. New deployments default to the latest stable minor in the 3.0.x line.
2. The pin is recorded in the orchestrator manifest and validated by the platform reconciliation loop.
3. Workloads that depend on legacy classic operators may pin to the 2.11.x LTS line for the lifetime of the LTS window.
4. Pre-release builds are restricted to evaluation deployments and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor (LTS)** — applied within 90 days.
- **Minor (non-LTS)** — applied within 180 days, after running the cross-version DAG-parity regression suite and the metadata-database migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises DAG export / import, executor migration, and metadata-database schema upgrade.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Deployments on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new DAGs cannot be registered on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| `apache-airflow` Python package | matches server version | SDK must match server major and minor. |
| Webserver / API server | matches SDK version | Airflow 3 separates API server from webserver. |
| Scheduler | matches SDK version | DAG parsing and task scheduling. |
| Executors | SequentialExecutor, LocalExecutor, CeleryExecutor, KubernetesExecutor, CeleryKubernetesExecutor | Selection recorded in the orchestrator manifest. |
| Providers | independently versioned | Pinned per deployment and validated against the SDK major. |
| Metadata database | PostgreSQL 14, 15, 16; MySQL 8.x | Required; see [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md). |

## Security and compliance

- TLS is mandatory for all SDK, webserver, and scheduler traffic.
- DAG-level access is gated by RBAC; legacy single-user access is deprecated.
- Connections and Variables are stored in the metadata database or an external secret backend; plaintext credentials in DAG files are prohibited.
- Audit logging is wired through the standard log pipeline; DAG-run-level audit events must include `dag_id`, `task_id`, `actor`, `operation`, and `run_id`.
- Personal data flowing through Airflow tasks is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the webserver / API server metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Task and scheduler traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for DAG-run duration, scheduler heartbeat, and executor saturation live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Dagster Data Orchestrator Version Governance](DAGSTER_VERSION_GOVERNANCE.md)
- [Prefect Workflow Orchestrator Version Governance](PREFECT_VERSION_GOVERNANCE.md)
- [Temporal Durable Execution Version Governance](TEMPORAL_VERSION_GOVERNANCE.md)
- [Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance](ARGO_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
