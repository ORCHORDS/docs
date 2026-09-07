# Vector Embedding Lineage Governance

## 1. Scope

Govern the lineage, versioning, and reproducibility of vector embeddings produced by OrchestrAI pipelines. Covers embedding model registration, dataset snapshotting, vector-to-source traceability, and re-embedding procedures triggered by model upgrade or dataset refresh.

Excludes the model-training process itself, which is governed by [AI Model Lifecycle Management Playbook](../playbooks/AI_MODEL_LIFECYCLE_PLAYBOOK.md) and the underlying AI risk and security standards.

## 2. Normative references

- [Vector Retrieval Governance](VECTOR_RETRIEVAL_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [AI Content Provenance Governance](AI_CONTENT_PROVENANCE_GOVERNANCE.md)
- [NIST SP 800-218A GenAI Profile Version Governance](NIST_SP_800_218A_GENAI_PROFILE_VERSION_GOVERNANCE.md)
- [ISO/IEC 42001:2023 AIMS Governance](ISO_IEC_42001_2023_AIMS_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Embedding model version** — an immutable identifier for the model architecture, weights, tokenizer, and pre/post-processing pipeline that produced a vector.
- **Dataset snapshot** — a content-addressed bundle of source records used to generate a vector collection.
- **Lineage record** — metadata that links each vector to its source record, embedding model version, dataset snapshot, and pipeline run.
- **Re-embedding** — the controlled regeneration of a collection after a change to the model version, tokenizer, or dataset snapshot.

## 4. Embedding model registration

1. Every embedding model used in production is registered in the Model Registry with a semantic version (`<major>.<minor>.<patch>`), a content hash, and a model card.
2. Major and minor bumps require a model-card review by the AI Governance Council.
3. Patch bumps are permitted without governance review but must be recorded in the change log.
4. Deprecated models are flagged for 90 days before retirement; new vector collections cannot use a deprecated model.

## 5. Dataset snapshotting

1. Every embedding pipeline run consumes a named, content-addressed dataset snapshot.
2. Snapshots are immutable and stored in object storage with object-lock retention of at least 12 months.
3. A snapshot's lineage record contains its source URI, capture timestamp, hash, and the schema used at capture time.
4. Personal-data snapshots are subject to the same retention and deletion rules as the source system; deletion propagates to derived embeddings.

## 6. Lineage record

1. Every vector persisted to a collection carries a lineage record with `collection`, `vector_id`, `source_id`, `source_snapshot`, `model_version`, `pipeline_run`, and `created_at`.
2. The lineage record is stored alongside the vector payload (Milvus payload field, Qdrant payload field, or pgvector metadata column).
3. The lineage record is mandatory; vectors without a complete lineage record are rejected at write time.
4. Lineage records are replicated to the central audit pipeline and retained for 24 months.

## 7. Reproducibility

1. Given a lineage record, the embedding pipeline must be able to reproduce the original vector deterministically from the source record, model version, and pipeline run.
2. Determinism is validated by re-embedding a sample of at least 100 vectors per collection each quarter and comparing the cosine distance.
3. Non-determinism greater than 1e-6 cosine distance opens a remediation ticket and blocks the model version from new collections until resolved.

## 8. Re-embedding procedure

1. Re-embedding is triggered by a model version change, tokenizer change, dataset refresh, or recall regression.
2. The migration plan must specify the source and target collections, the batch size, the cutover strategy (dual-write + switch, or shadow + cutover), and the rollback procedure.
3. Old embeddings are quarantined in a sibling collection until the new embeddings are validated against the recall budget.
4. Re-embedding progress is reported on the workload dashboard; abort criteria are declared before the run starts.

## 9. Provenance and audit

1. The lineage record satisfies the provenance requirements of [AI Content Provenance Governance](AI_CONTENT_PROVENANCE_GOVERNANCE.md) for retrieval-augmented outputs.
2. Regulated workloads must retain lineage records for the duration mandated by the applicable regulation; the default is 24 months.
3. Auditors can request a reverse lookup (vector → source record) using the lineage record; the lookup must complete within 5 seconds for any single vector.
4. Personal-data deletion requests are propagated via the lineage record; see [Vector Retrieval Governance](VECTOR_RETRIEVAL_GOVERNANCE.md).

## 10. Security

1. Embedding pipelines run in isolated execution environments with no network egress to non-approved destinations.
2. Source records processed by the pipeline are encrypted at rest; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. The model registry and dataset snapshot store are access-controlled and audited.
4. LLM-specific threats (prompt injection, embedding inversion) are tracked under [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md).

## 11. Operating model

1. The Embedding Platform team owns the pipeline infrastructure, the model registry, and the snapshot store.
2. Workload owners own the dataset snapshots and the collection schema.
3. AI Governance Council approves major model version bumps and re-embedding migrations that affect regulated workloads.
4. The Embedding Platform guild meets monthly to review pipeline performance, cost, and adoption of new models.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
