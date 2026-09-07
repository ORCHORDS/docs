# Workflow Orchestrator Adoption Playbook

## Purpose

Adopt a workflow orchestrator (Dagster, Prefect, Apache Airflow, Temporal, Argo Workflows, or managed equivalent) for a new workload that requires scheduling, retry semantics, and integration with feature, vector, and model serving subsystems. The playbook aligns with [Workflow Orchestrator Architecture Governance](../standards/WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md), [Workflow Lineage & Reproducibility Governance](../standards/WORKFLOW_LINEAGE_REPRODUCIBILITY_GOVERNANCE.md), and [Workflow Orchestrator Access Control Governance](../standards/WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md).

## Audience

Workflow owners, data engineers, ML platform engineers, security reviewers.

## Pre-conditions

1. The orchestrator reference card is current (`DAGSTER_VERSION_GOVERNANCE.md`, `PREFECT_VERSION_GOVERNANCE.md`, `AIRFLOW_VERSION_GOVERNANCE.md`, `TEMPORAL_VERSION_GOVERNANCE.md`, `ARGO_VERSION_GOVERNANCE.md`).
2. AI Impact Assessment is filed for the workload; see [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md).
3. Tenant scoping and data-classification decisions are documented.
4. Source datasets are registered in the catalogue with documented freshness and retention.
5. Downstream consumer list (feature store, vector store, model registry) is documented.

## Procedure

1. **Select the orchestrator.** Choose Dagster for asset-centric data + ML; Prefect for dynamic Python-native; Airflow for mature provider ecosystem; Temporal for durable long-running business workflows; Argo Workflows for Kubernetes-native CI / CD and ML training.
2. **Provision the cluster.** Apply the platform Helm chart or Terraform module pinned to the supported minor; record the orchestrator manifest in the inventory.
3. **Configure authentication and authorization.** Provision workload-scoped service-account credentials in the central secret backend; enable OIDC for interactive users; disable legacy username/password authentication.
4. **Configure the secret backend.** Wire the central secret backend as the source of truth for connections, variables, and parameters; verify secret rotation propagates to running workers.
5. **Author the workflow definitions.** Declare each workflow's name, version, owner, AI risk tier, schedule, executor, work pool, runtime SLO, and downstream consumer list. Register the workflow in the Workflow Platform registry.
6. **Wire lineage.** Emit lineage records with every run; reject outputs without a complete lineage record; wire the central audit pipeline.
7. **Wire observability.** Enable Prometheus metrics, OTLP traces, runtime SLO dashboards, and schedule-failure alerts following the standard observability requirements.
8. **Run a security review.** Walk through the [Workflow Orchestrator Access Control Governance](../standards/WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md) threat model; document mitigations and residual risk; file waivers for any unmet controls.
9. **Pilot in staging.** Route 5% of production traffic to the staging cluster; compare runtime SLOs, schedule reliability, and downstream freshness with the baseline.
10. **Promote to production.** Enable the production cluster; set the runtime SLO alert, the schedule-failure alert, and the lineage-integrity alert; hand off to the on-call rotation.
11. **Adopt the operating cadence.** Schedule the quarterly determinism regression, the annual threat-model review, and the 180-day standard review.

## Rollback

1. Pause the workflows via the orchestrator's pause API.
2. Switch the workload back to the previous scheduling source (cron, manual triggers, or prior orchestrator).
3. Quarantine the workflow definitions for forensic review; do not delete until the security review is complete.
4. Open a remediation ticket that captures the runtime SLO breach, the lineage breach, or the security finding.
5. Communicate the rollback to stakeholders via the standard incident communication channel.
6. Update the workload specification with the lessons learned before the next adoption attempt.

## References

- [Workflow Orchestrator Architecture Governance](../standards/WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md)
- [Workflow Lineage & Reproducibility Governance](../standards/WORKFLOW_LINEAGE_REPRODUCIBILITY_GOVERNANCE.md)
- [Workflow Orchestrator Access Control Governance](../standards/WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md)
- [Dagster Data Orchestrator Version Governance](../reference/DAGSTER_VERSION_GOVERNANCE.md)
- [Prefect Workflow Orchestrator Version Governance](../reference/PREFECT_VERSION_GOVERNANCE.md)
- [Apache Airflow Workflow Orchestrator Version Governance](../reference/AIRFLOW_VERSION_GOVERNANCE.md)
- [Temporal Durable Execution Version Governance](../reference/TEMPORAL_VERSION_GOVERNANCE.md)
- [Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance](../reference/ARGO_VERSION_GOVERNANCE.md)
- [Feature Pipeline Lineage Governance](../standards/FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](../standards/VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
