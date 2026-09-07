# Workflow Orchestrator Architecture Governance

## 1. Scope

Govern the architecture, selection, and operational use of workflow orchestrators (Dagster, Prefect, Apache Airflow, Temporal, Argo Workflows, and managed equivalents) across OrchestrAI products. Covers DAG / flow / asset definitions, executor selection, scheduling, and integration with feature, vector, and model serving subsystems.

Excludes the underlying compute engines (Kubernetes, Databricks, Spark) which are governed by their own cards. Excludes pipeline-specific lineage and access-control standards, which are covered by [Workflow Lineage & Reproducibility Governance](WORKFLOW_LINEAGE_REPRODUCIBILITY_GOVERNANCE.md) and [Workflow Orchestrator Access Control Governance](WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md).

## 2. Normative references

- [Dagster Data Orchestrator Version Governance](../reference/DAGSTER_VERSION_GOVERNANCE.md)
- [Prefect Workflow Orchestrator Version Governance](../reference/PREFECT_VERSION_GOVERNANCE.md)
- [Apache Airflow Workflow Orchestrator Version Governance](../reference/AIRFLOW_VERSION_GOVERNANCE.md)
- [Temporal Durable Execution Version Governance](../reference/TEMPORAL_VERSION_GOVERNANCE.md)
- [Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance](../reference/ARGO_VERSION_GOVERNANCE.md)
- [Workflow Lineage & Reproducibility Governance](WORKFLOW_LINEAGE_REPRODUCIBILITY_GOVERNANCE.md)
- [Workflow Orchestrator Access Control Governance](WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)

## 3. Terms and definitions

- **DAG / flow / asset graph** — the directed graph of compute units that define a workflow.
- **Executor** — the component that schedules and runs compute units on a target compute engine.
- **Schedule** — a declarative trigger (cron, interval, or event-based) that launches a workflow.
- **Sensor / watcher** — a long-running component that observes external state and triggers workflows in response.
- **Work pool / code location** — a deployment-target abstraction that maps workflows to compute engines.

## 4. Orchestrator selection

1. Dagster is preferred for asset-centric data + ML workloads that need first-class lineage between code, data assets, and compute.
2. Prefect is preferred for dynamic, Python-native workloads that need lightweight serverless execution and managed work pools.
3. Apache Airflow is preferred for mature provider ecosystem, broad executor coverage, and DAG-as-code parity with the broader industry.
4. Temporal is preferred for long-running, durable business workflows that require workflow-as-code and automatic retry.
5. Argo Workflows is preferred for Kubernetes-native CI / CD and ML training workloads.
6. The choice is recorded in the orchestrator manifest and reviewed annually.

## 5. Workflow definition contract

1. Every workflow declares its name, version, owner, AI risk tier, schedule (or trigger), executor, work pool / code location, expected runtime SLO, and downstream consumer list.
2. Workflow versions are immutable; breaking changes require a new major version.
3. Backwards-compatible additions (new tasks, new parameters) are permitted under a new minor version.
4. Deprecated workflows remain runnable for at least 180 days after deprecation; the deprecation date and the migration target are recorded in the manifest.

## 6. Executor selection

1. The executor is selected per workflow based on the workload's compute pattern, isolation requirements, and cost envelope.
2. The choice is recorded in the orchestrator manifest; runtime override is prohibited without a change ticket.
3. KubernetesExecutor and k8s-based work pools are the default for production workloads that require per-task isolation.
4. LocalExecutor and in-process executors are permitted only for evaluation deployments and never promoted to production.

## 7. Scheduling and sensors

1. Schedules are declared in the workflow definition and recorded in the manifest; ad-hoc triggers via the API are permitted but must be logged.
2. Sensors observe external state with a polling interval declared in the workflow definition; sub-10-second polling requires a documented justification.
3. Sensor failures must produce an alert within the standard incident cadence; chronic sensor failures trigger a workflow-contract review.
4. Backfills must use the orchestrator's native backfill API; ad-hoc backfills via direct database writes are prohibited.

## 8. Integration with downstream subsystems

1. Workflows that produce feature values must follow [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md) for lineage emission.
2. Workflows that produce embeddings must follow [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md) for lineage emission.
3. Workflows that register or deploy models must follow [AI Model Lifecycle Management Playbook](../playbooks/AI_MODEL_LIFECYCLE_PLAYBOOK.md) for model registration.
4. Cross-subsystem integration is wired through the orchestrator manifest and validated at adoption time.

## 9. Reliability and observability

1. Workflows must declare an expected runtime SLO; chronic breaches trigger a workflow-contract review.
2. DAG-run, flow-run, and workflow-run events are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
3. SLOs are defined per workflow using the standard SLO template; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
4. Dashboards and alerts are owned by the workflow owner; see [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md) and [Prometheus Alerting Adoption Playbook](../playbooks/PROMETHEUS_ALERTING_ADOPTION_PLAYBOOK.md).

## 10. Security

1. TLS is required for all SDK, server, and worker traffic.
2. Access to workflows is gated by RBAC; legacy single-user access is deprecated.
3. Personal data in workflows is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Workflow-level access control is governed by [Workflow Orchestrator Access Control Governance](WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md).

## 11. Operating model

1. The Workflow Platform team owns the shared orchestrator infrastructure and the reference executor configurations.
2. Workflow owners own their workflow definitions, schedules, and runtime SLOs.
3. The Workflow Platform guild meets monthly to review runtime regressions, capacity, and adoption of new orchestrators.
4. New orchestrator vendors are evaluated by the Workflow Platform team and approved by the AI Governance Council.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
