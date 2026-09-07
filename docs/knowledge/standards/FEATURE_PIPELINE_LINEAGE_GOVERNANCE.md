# Feature Pipeline Lineage Governance

## 1. Scope

Govern the lineage, versioning, and reproducibility of feature pipelines (Feast, Tecton, Hopsworks Feature Store, and equivalents) across OrchestrAI products. Covers transformation registration, dataset snapshotting, feature-to-source traceability, and backfill procedures triggered by feature-view version change or dataset refresh.

Excludes the model-training process itself, which is governed by [AI Model Lifecycle Management Playbook](../playbooks/AI_MODEL_LIFECYCLE_PLAYBOOK.md). Excludes embedding pipelines, which are governed by [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md).

## 2. Normative references

- [Feature Store Architecture Governance](FEATURE_STORE_ARCHITECTURE_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-218A GenAI Profile Version Governance](NIST_SP_800_218A_GENAI_PROFILE_VERSION_GOVERNANCE.md)
- [ISO/IEC 42001:2023 AIMS Governance](ISO_IEC_42001_2023_AIMS_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Transformation version** — an immutable identifier for the code, parameters, and runtime that compute a feature.
- **Feature-view snapshot** — a content-addressed bundle of source records used to materialise a feature view at a point in time.
- **Lineage record** — metadata that links each feature value to its source record, transformation version, snapshot, and pipeline run.
- **Backfill** — the controlled regeneration of historical feature values after a transformation version change or source snapshot refresh.

## 4. Transformation registration

1. Every transformation used in a feature view is registered in the Feature Platform registry with a semantic version (`<major>.<minor>.<patch>`), a content hash, and a transformation card.
2. Major and minor bumps require a transformation-card review by the Feature Platform guild.
3. Patch bumps are permitted without review but must be recorded in the change log.
4. Deprecated transformations are flagged for 90 days before retirement; new feature views cannot reference a deprecated transformation.

## 5. Feature-view snapshotting

1. Every materialisation pipeline run consumes a named, content-addressed snapshot.
2. Snapshots are immutable and stored in object storage with object-lock retention of at least 12 months.
3. A snapshot's lineage record contains its source URI, capture timestamp, hash, and the schema used at capture time.
4. Personal-data snapshots are subject to the same retention and deletion rules as the source system; deletion propagates to derived feature values.

## 6. Lineage record

1. Every feature value persisted to the offline store carries a lineage record with `feature_view`, `feature_version`, `entity_key`, `source_id`, `source_snapshot`, `transformation_version`, `pipeline_run`, and `created_at`.
2. The lineage record is stored alongside the feature value in the offline store (a sidecar column or metadata table).
3. The lineage record is mandatory; feature values without a complete lineage record are rejected at write time.
4. Lineage records are replicated to the central audit pipeline and retained for 24 months.

## 7. Reproducibility

1. Given a lineage record, the transformation pipeline must be able to reproduce the original feature value deterministically from the source record, transformation version, and pipeline run.
2. Determinism is validated by re-running a sample of at least 100 entity keys per feature view each quarter and comparing values within the declared tolerance.
3. Non-determinism above the declared tolerance opens a remediation ticket and blocks the transformation version from new feature views until resolved.

## 8. Backfill procedure

1. Backfill is triggered by a transformation version change, source snapshot refresh, or parity regression.
2. The migration plan must specify the source and target feature-view versions, the batch size, the cutover strategy (dual-write + switch, or shadow + cutover), and the rollback procedure.
3. Old feature values are quarantined until the new values are validated against the parity contract.
4. Backfill progress is reported on the workload dashboard; abort criteria are declared before the run starts.

## 9. Provenance and audit

1. The lineage record satisfies the provenance requirements of [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md) for features consumed by regulated models.
2. Regulated workloads must retain lineage records for the duration mandated by the applicable regulation; the default is 24 months.
3. Auditors can request a reverse lookup (feature value → source record) using the lineage record; the lookup must complete within 5 seconds for any single entity key.
4. Personal-data deletion requests are propagated via the lineage record; see [Feature Store Architecture Governance](FEATURE_STORE_ARCHITECTURE_GOVERNANCE.md).

## 10. Security

1. Transformation code runs in isolated execution environments with no network egress to non-approved destinations.
2. Source records processed by the pipeline are encrypted at rest; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. The transformation registry and the snapshot store are access-controlled and audited.
4. Vector embeddings derived from feature views are governed by [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md).

## 11. Operating model

1. The Feature Platform team owns the transformation registry and the snapshot store.
2. Workload owners own the source snapshots and the feature-view definitions.
3. AI Governance Council approves major transformation bumps and backfills that affect regulated workloads.
4. The Feature Platform guild meets monthly to review pipeline performance, cost, and adoption of new transformations.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
