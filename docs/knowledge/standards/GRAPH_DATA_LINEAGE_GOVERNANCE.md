# Graph Data Lineage Governance

## 1. Scope

Govern the lineage, versioning, and reproducibility of graph data (Neo4j, Amazon Neptune, Memgraph, and equivalents) across OrchestrAI products. Covers graph schema versioning, dataset snapshotting, graph-element-to-source traceability, and migration procedures triggered by schema version change or dataset refresh.

Excludes the model-training process itself, which is governed by [AI Model Lifecycle Management Playbook](../playbooks/AI_MODEL_LIFECYCLE_PLAYBOOK.md). Excludes embedding pipelines, which are governed by [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md). Excludes feature pipelines, which are governed by [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md).

## 2. Normative references

- [Graph Database Architecture Governance](GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Graph Query Safety & Performance Governance](GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md)
- [Neo4j Graph Database Version Governance](../reference/NEO4J_VERSION_GOVERNANCE.md)
- [Amazon Neptune Graph Database Version Governance](../reference/NEPTUNE_VERSION_GOVERNANCE.md)
- [Memgraph In-Memory Graph Database Version Governance](../reference/MEMGRAPH_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md)
- [NIST SP 800-218A GenAI Profile Version Governance](NIST_SP_800_218A_GENAI_PROFILE_VERSION_GOVERNANCE.md)
- [ISO/IEC 42001:2023 AIMS Governance](ISO_IEC_42001_2023_AIMS_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Graph schema version** — an immutable identifier for the node labels, relationship types, property keys, indexes, and constraints that define a graph.
- **Graph snapshot** — a content-addressed export of a graph database at a point in time, stored as a single file or set of files in object storage.
- **Lineage record** — metadata that links each graph element to its source record, schema version, snapshot, and pipeline run.
- **Graph migration** — the controlled evolution of a graph from one schema version to the next.

## 4. Graph schema versioning

1. Every production schema is registered in the Graph Platform registry with a semantic version (`<major>.<minor>.<patch>`), a content hash, and a schema card.
2. Major and minor bumps require a schema-card review by the Graph Platform guild.
3. Patch bumps are permitted without review but must be recorded in the change log.
4. Deprecated schemas are flagged for 90 days before retirement; new graphs cannot reference a deprecated schema.

## 5. Graph snapshotting

1. Every graph migration or load job consumes a named, content-addressed snapshot.
2. Snapshots are immutable and stored in object storage with object-lock retention of at least 12 months; see [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
3. A snapshot's lineage record contains its source URI, capture timestamp, hash, and the schema used at capture time.
4. Personal-data snapshots are subject to the same retention and deletion rules as the source system; deletion propagates to derived graph elements.

## 6. Lineage record

1. Every graph element persisted to a production schema carries a lineage record with `schema_version`, `node_label`, `relationship_type`, `source_id`, `source_snapshot`, `pipeline_run`, and `created_at`.
2. The lineage record is stored as a graph property on the element itself, or in a sidecar table linked by element ID.
3. The lineage record is mandatory; elements without a complete lineage record are rejected at write time.
4. Lineage records are replicated to the central audit pipeline and retained for 24 months.

## 7. Reproducibility

1. Given a lineage record, the load pipeline must be able to reproduce the original graph element deterministically from the source record, schema version, and pipeline run.
2. Determinism is validated by re-running a sample of at least 100 elements per graph each quarter and comparing element identity.
3. Non-determinism above the declared tolerance opens a remediation ticket and blocks the schema version from new graphs until resolved.

## 8. Graph migration procedure

1. Migration is triggered by a schema version change, source snapshot refresh, or graph-element regression.
2. The migration plan must specify the source and target schema versions, the cutover strategy (dual-write + switch, or shadow + cutover), the batch size, and the rollback procedure.
3. Old graph elements are quarantined until the new elements are validated against the schema contract.
4. Migration progress is reported on the workload dashboard; abort criteria are declared before the run starts.

## 9. Provenance and audit

1. The lineage record satisfies the provenance requirements of [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md) for graphs consumed by regulated models.
2. Regulated workloads must retain lineage records for the duration mandated by the applicable regulation; the default is 24 months.
3. Auditors can request a reverse lookup (graph element → source record) using the lineage record; the lookup must complete within 5 seconds for any single element.
4. Personal-data deletion requests are propagated via the lineage record; see [Graph Database Architecture Governance](GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md).

## 10. Security

1. Load pipelines run in isolated execution environments with no network egress to non-approved destinations.
2. Source records processed by the pipeline are encrypted at rest; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. The schema registry and the snapshot store are access-controlled and audited.
4. Vector embeddings derived from graph elements are governed by [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md).
5. Feature values derived from graph elements are governed by [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md).

## 11. Operating model

1. The Graph Platform team owns the schema registry and the snapshot store.
2. Workload owners own the source snapshots and the schema definitions.
3. AI Governance Council approves major schema bumps and migrations that affect regulated workloads.
4. The Graph Platform guild meets monthly to review pipeline performance, cost, and adoption of new graph patterns.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
