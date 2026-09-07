# Workflow Lineage & Reproducibility Governance

## 1. Scope

Govern the lineage, versioning, and reproducibility of workflows running on Dagster, Prefect, Apache Airflow, Temporal, Argo Workflows, and managed equivalents across OrchestrAI products. Covers task registration, dataset / asset snapshotting, workflow-to-source traceability, and backfill procedures triggered by workflow version change or dataset refresh.

Excludes the model-training process itself, which is governed by [AI Model Lifecycle Management Playbook](../playbooks/AI_MODEL_LIFECYCLE_PLAYBOOK.md). Excludes embedding pipelines, which are governed by [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md). Excludes feature pipelines, which are governed by [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md).

## 2. Normative references

- [Workflow Orchestrator Architecture Governance](WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md)
- [Workflow Orchestrator Access Control Governance](WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md)
- [Dagster Data Orchestrator Version Governance](../reference/DAGSTER_VERSION_GOVERNANCE.md)
- [Prefect Workflow Orchestrator Version Governance](../reference/PREFECT_VERSION_GOVERNANCE.md)
- [Apache Airflow Workflow Orchestrator Version Governance](../reference/AIRFLOW_VERSION_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-218A GenAI Profile Version Governance](NIST_SP_800_218A_GENAI_PROFILE_VERSION_GOVERNANCE.md)
- [ISO/IEC 42001:2023 AIMS Governance](ISO_IEC_42001_2023_AIMS_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Workflow version** — an immutable identifier for the code, parameters, and runtime that define a workflow.
- **Dataset / asset snapshot** — a content-addressed bundle of source records used by a workflow run.
- **Lineage record** — metadata that links each workflow output to its source data, workflow version, snapshot, and run.
- **Backfill** — the controlled regeneration of historical workflow outputs after a workflow version change or dataset refresh.

## 4. Workflow registration

1. Every workflow used in production is registered in the Workflow Platform registry with a semantic version (`<major>.<minor>.<patch>`), a content hash, and a workflow card.
2. Major and minor bumps require a workflow-card review by the Workflow Platform guild.
3. Patch bumps are permitted without review but must be recorded in the change log.
4. Deprecated workflows are flagged for 90 days before retirement; new workflows cannot reference a deprecated workflow.

## 5. Dataset / asset snapshotting

1. Every workflow run consumes a named, content-addressed dataset / asset snapshot.
2. Snapshots are immutable and stored in object storage with object-lock retention of at least 12 months.
3. A snapshot's lineage record contains its source URI, capture timestamp, hash, and the schema used at capture time.
4. Personal-data snapshots are subject to the same retention and deletion rules as the source system; deletion propagates to derived outputs.

## 6. Lineage record

1. Every workflow output persisted to a downstream system carries a lineage record with `workflow`, `workflow_version`, `task`, `source_id`, `source_snapshot`, `pipeline_run`, `run_id`, and `created_at`.
2. The lineage record is stored alongside the output (a sidecar column, a metadata file, or a registry entry) and emitted to the central audit pipeline.
3. The lineage record is mandatory; outputs without a complete lineage record are rejected at write time.
4. Lineage records are retained for 24 months.

## 7. Reproducibility

1. Given a lineage record, the workflow must be able to reproduce the original output deterministically from the source data, workflow version, and run.
2. Determinism is validated by re-running a sample of at least 100 outputs per workflow each quarter and comparing values within the declared tolerance.
3. Non-determinism above the declared tolerance opens a remediation ticket and blocks the workflow version from new runs until resolved.

## 8. Backfill procedure

1. Backfill is triggered by a workflow version change, source snapshot refresh, or output regression.
2. The migration plan must specify the source and target workflow versions, the batch size, the cutover strategy (dual-write + switch, or shadow + cutover), and the rollback procedure.
3. Old outputs are quarantined until the new outputs are validated against the workflow's parity contract.
4. Backfill progress is reported on the workload dashboard; abort criteria are declared before the run starts.

## 9. Provenance and audit

1. The lineage record satisfies the provenance requirements of [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md) for workflows consumed by regulated models.
2. Regulated workloads must retain lineage records for the duration mandated by the applicable regulation; the default is 24 months.
3. Auditors can request a reverse lookup (workflow output → source record) using the lineage record; the lookup must complete within 5 seconds for any single output.
4. Personal-data deletion requests are propagated via the lineage record; see [Workflow Orchestrator Architecture Governance](WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md).

## 10. Security

1. Workflow code runs in isolated execution environments with no network egress to non-approved destinations.
2. Source records processed by the workflow are encrypted at rest; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. The workflow registry and the snapshot store are access-controlled and audited.
4. Vector embeddings derived from workflow outputs are governed by [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md).
5. Feature values derived from workflow outputs are governed by [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md).

## 11. Operating model

1. The Workflow Platform team owns the workflow registry and the snapshot store.
2. Workflow owners own the source snapshots and the workflow definitions.
3. AI Governance Council approves major workflow bumps and backfills that affect regulated workloads.
4. The Workflow Platform guild meets monthly to review pipeline performance, cost, and adoption of new workflow patterns.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
