# Workflow Migration Playbook

## Purpose

Migrate an existing workflow from one orchestrator (or one orchestrator version) to a new orchestrator (or new orchestrator version) while preserving the workload's runtime SLO, lineage integrity, and tenant-scoping guarantees. The playbook aligns with [Workflow Orchestrator Architecture Governance](../standards/WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md), [Workflow Lineage & Reproducibility Governance](../standards/WORKFLOW_LINEAGE_REPRODUCIBILITY_GOVERNANCE.md), and [Workflow Orchestrator Access Control Governance](../standards/WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md).

## Audience

Workflow owners, data engineers, ML platform engineers, Workflow Platform engineers, AI Governance Council reviewers.

## Pre-conditions

1. The target orchestrator and version are registered in the Workflow Platform registry with a documented workflow card.
2. The target source snapshot (if any) is captured, content-addressed, and frozen in the snapshot store.
3. The runtime SLO and the lineage contract for the workload are documented; the evaluation set is current.
4. A staging replica of the source workflow is available for the rehearsal run.
5. Security review is complete for any change that affects personal-data outputs.

## Procedure

1. **Scope the migration.** Identify the source and target workflow versions, the cutover strategy (dual-write + switch, or shadow + cutover), the batch size, and the abort criteria. Record the plan in the migration ticket.
2. **Rehearse in staging.** Run the workflow against the staging snapshot; emit lineage records; measure runtime SLO, determinism, and downstream freshness against the existing workflow. Resolve any regression before the production run.
3. **Provision the target workflow.** Register the target workflow with the new version, executor, and runtime SLO. Validate that the access layer rejects triggers without a tenant parameter.
4. **Run the production workflow in shadow mode.** Configure the application to trigger both workflows; the source workflow continues to serve production traffic while the target workflow runs in parallel for verification.
5. **Validate during shadow runs.** Sample at least 100 outputs per batch and compare runtime, determinism, and downstream freshness against the baseline. Halt the run if any metric regresses by more than the abort criterion.
6. **Cut over.** Switch the production trigger to the target workflow; keep dual-writes or shadow reads active for at least 24 hours to catch late-arriving outputs.
7. **Quarantine the source workflow.** Mark the source workflow as `deprecated`; retain the code and configuration for at least 30 days; do not delete until the migration is signed off.
8. **Sign off.** Confirm the runtime SLO is met, lineage records are complete, and downstream freshness is within tolerance; close the migration ticket.
9. **Decommission the source workflow.** After the quarantine window, archive the source workflow definitions and lineage records following the data-lifecycle procedure.

## Rollback

1. Stop the target workflow and freeze its triggers.
2. Switch the production trigger back to the source workflow.
3. If dual-write was not active, restore the downstream outputs from the most recent snapshot; document the data gap.
4. Open a remediation ticket that captures the regression metric, the abort criterion that was triggered, and the proposed fix.
5. Communicate the rollback to stakeholders and reschedule the migration after the fix is verified.

## References

- [Workflow Orchestrator Architecture Governance](../standards/WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md)
- [Workflow Lineage & Reproducibility Governance](../standards/WORKFLOW_LINEAGE_REPRODUCIBILITY_GOVERNANCE.md)
- [Workflow Orchestrator Access Control Governance](../standards/WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md)
- [Dagster Data Orchestrator Version Governance](../reference/DAGSTER_VERSION_GOVERNANCE.md)
- [Prefect Workflow Orchestrator Version Governance](../reference/PREFECT_VERSION_GOVERNANCE.md)
- [Apache Airflow Workflow Orchestrator Version Governance](../reference/AIRFLOW_VERSION_GOVERNANCE.md)
- [Temporal Durable Execution Version Governance](../reference/TEMPORAL_VERSION_GOVERNANCE.md)
- [Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance](../reference/ARGO_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
