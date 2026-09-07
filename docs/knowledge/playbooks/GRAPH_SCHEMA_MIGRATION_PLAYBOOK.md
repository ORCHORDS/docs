# Graph Schema Migration Playbook

## Purpose

Migrate an existing graph schema (Neo4j, Amazon Neptune, Memgraph) to a new schema version while preserving the workload's query-latency SLO, lineage integrity, and tenant-scoping guarantees. The playbook aligns with [Graph Data Lineage Governance](../standards/GRAPH_DATA_LINEAGE_GOVERNANCE.md) and [Graph Database Architecture Governance](../standards/GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md).

## Audience

Workload owners, Graph Platform engineers, data engineers, AI Governance Council reviewers.

## Pre-conditions

1. The target schema version is registered in the Graph Platform registry with a documented schema card.
2. The target source snapshot is captured, content-addressed, and frozen in the snapshot store.
3. The query-latency SLO and the lineage contract for the workload are documented; the evaluation query set is current.
4. A staging replica of the source graph is available for the rehearsal run.
5. Security review is complete for any change that affects personal-data elements.

## Procedure

1. **Scope the migration.** Identify the source and target schema versions, the cutover strategy (dual-write + switch, or shadow + cutover), the batch size, and the abort criteria. Record the plan in the migration ticket.
2. **Rehearse in staging.** Run the load pipeline against the staging snapshot; emit lineage records; measure query latency, determinism, and tenant scoping against the existing schema. Resolve any regression before the production run.
3. **Provision the target schema.** Apply the target schema version with the new labels, relationships, properties, indexes, and constraints. Validate that the access layer rejects queries without a tenant filter.
4. **Run the production migration job.** Process the source snapshot in batches; write elements and lineage records to the target schema. Surface progress on the workload dashboard.
5. **Validate during the run.** Sample at least 100 elements per batch and compare query latency, determinism, and tenant scoping against the baseline. Halt the run if any metric regresses by more than the abort criterion.
6. **Wire dual-write or shadow reads.** Configure the application to write to both schemas and read from the source schema until the cutover is approved.
7. **Cut over.** Switch reads to the target schema; keep dual-writes active for at least 24 hours to catch late-arriving elements.
8. **Quarantine the source schema.** Mark the source schema as `deprecated`; retain the data for at least 30 days; do not delete until the migration is signed off.
9. **Sign off.** Confirm the query-latency SLO is met, lineage records are complete, and tenant scoping is preserved; close the migration ticket.
10. **Decommission the source schema.** After the quarantine window, delete the source elements and lineage records following the data-lifecycle procedure.

## Rollback

1. Stop the migration job and freeze writes to the target schema.
2. Switch reads back to the source schema.
3. If dual-write was not active, restore the source schema from the most recent snapshot; document the data gap.
4. Open a remediation ticket that captures the regression metric, the abort criterion that was triggered, and the proposed fix.
5. Communicate the rollback to stakeholders and reschedule the migration after the fix is verified.

## References

- [Graph Data Lineage Governance](../standards/GRAPH_DATA_LINEAGE_GOVERNANCE.md)
- [Graph Database Architecture Governance](../standards/GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Graph Query Safety & Performance Governance](../standards/GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md)
- [Neo4j Graph Database Version Governance](../reference/NEO4J_VERSION_GOVERNANCE.md)
- [Amazon Neptune Graph Database Version Governance](../reference/NEPTUNE_VERSION_GOVERNANCE.md)
- [Memgraph In-Memory Graph Database Version Governance](../reference/MEMGRAPH_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
