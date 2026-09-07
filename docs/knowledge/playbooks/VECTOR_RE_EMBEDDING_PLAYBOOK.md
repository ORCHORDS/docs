# Vector Re-embedding Migration Playbook

## Purpose

Migrate an existing vector collection to a new embedding model version, tokenizer, or dataset snapshot while preserving the workload's recall budget and tenant-scoping guarantees. The playbook aligns with [Vector Embedding Lineage Governance](../standards/VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md) and [Vector Retrieval Governance](../standards/VECTOR_RETRIEVAL_GOVERNANCE.md).

## Audience

Workload owners, embedding pipeline engineers, Vector Platform engineers, AI Governance Council reviewers.

## Pre-conditions

1. The target embedding model version is registered in the Model Registry with a documented model card.
2. The target dataset snapshot is captured, content-addressed, and frozen in the snapshot store.
3. The recall budget for the workload is documented; the evaluation set is current and stored alongside the collection.
4. A staging replica of the source collection is available for the rehearsal run.
5. Security review is complete for any change that affects personal-data embeddings.

## Procedure

1. **Scope the migration.** Identify the source and target collections, the cutover strategy (dual-write + switch, or shadow + cutover), the batch size, and the abort criteria. Record the plan in the migration ticket.
2. **Rehearse in staging.** Run the embedding pipeline against the staging snapshot; emit lineage records; measure recall@K and determinism against the existing collection. Resolve any regression before the production run.
3. **Provision the target collection.** Create the target collection with the new vector dimension, distance metric, index parameters, and tenant-scope field. Validate that the access layer rejects queries without a tenant filter.
4. **Run the production embedding job.** Process the source snapshot in batches; write vectors and lineage records to the target collection. Surface progress on the workload dashboard.
5. **Validate during the run.** Sample at least 100 vectors per batch and compare determinism (cosine distance) and recall@K against the baseline. Halt the run if either regresses by more than the abort criterion.
6. **Wire dual-write or shadow reads.** Configure the application to write to both collections and read from the source until the cutover is approved.
7. **Cut over.** Switch reads to the target collection; keep dual-writes active for at least 24 hours to catch late-arriving records.
8. **Quarantine the source collection.** Mark the source collection as `quarantined`; retain the storage for at least 30 days; do not delete until the migration is signed off.
9. **Sign off.** Confirm the recall budget is met, lineage records are complete, and observability is wired; close the migration ticket.
10. **Decommission the source collection.** After the quarantine window, delete the source vectors and lineage records following the data-lifecycle procedure.

## Rollback

1. Stop the embedding job and freeze writes to the target collection.
2. Switch reads back to the source collection.
3. If dual-write was not active, restore the source collection from the most recent snapshot; document the data gap.
4. Open a remediation ticket that captures the regression metric, the abort criterion that was triggered, and the proposed fix.
5. Communicate the rollback to stakeholders and reschedule the migration after the fix is verified.

## References

- [Vector Embedding Lineage Governance](../standards/VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [Vector Retrieval Governance](../standards/VECTOR_RETRIEVAL_GOVERNANCE.md)
- [Vector Security Governance](../standards/VECTOR_SECURITY_GOVERNANCE.md)
- [Milvus Vector Database Version Governance](../reference/MILVUS_VERSION_GOVERNANCE.md)
- [Qdrant Vector Search Version Governance](../reference/QDRANT_VERSION_GOVERNANCE.md)
- [pgvector Version Governance](../reference/PGVECTOR_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
