# Vector Store Adoption Playbook

## Purpose

Adopt a vector database (Milvus, Qdrant, or pgvector) for a new retrieval-augmented generation (RAG), semantic search, or recommendation workload. The playbook aligns with [Vector Retrieval Governance](../standards/VECTOR_RETRIEVAL_GOVERNANCE.md), [Vector Embedding Lineage Governance](../standards/VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md), and [Vector Security Governance](../standards/VECTOR_SECURITY_GOVERNANCE.md).

## Audience

Workload owners, AI platform engineers, embedding pipeline engineers, security reviewers.

## Pre-conditions

1. The vector store reference card is current (`MILVUS_VERSION_GOVERNANCE.md`, `QDRANT_VERSION_GOVERNANCE.md`, `PGVECTOR_VERSION_GOVERNANCE.md`).
2. AI Impact Assessment is filed for the workload; see [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md).
3. Tenant scoping and data-classification decisions are documented.
4. Embedding model version is registered in the Model Registry; see [Vector Embedding Lineage Governance](../standards/VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md).
5. A representative evaluation set of at least 1,000 queries is available or scheduled for capture.

## Procedure

1. **Select the store.** Choose Milvus for very large collections (>50 million vectors) or hybrid sparse+dense requirements; choose Qdrant for single-node simplicity and payload filtering; choose pgvector when co-location with relational metadata is required.
2. **Provision the cluster.** Apply the platform Helm chart or Terraform module pinned to the supported minor; record the cluster manifest in the inventory.
3. **Configure authentication.** Provision workload-scoped API keys in the central secret manager; disable legacy username/password authentication.
4. **Define the collection schema.** Declare the vector dimension, distance metric, index type, index parameters, payload schema, and tenant-scope field. Validate against the standard's index-selection rules.
5. **Wire the embedding pipeline.** Connect the registered embedding model version; emit lineage records with every write; reject writes without a complete lineage record.
6. **Backfill the evaluation set.** Index the representative evaluation set; measure baseline recall@K and document the recall budget.
7. **Wire observability.** Enable Prometheus metrics, OTLP traces, and SLO dashboards following the standard observability requirements.
8. **Run a security review.** Walk through the [Vector Security Governance](../standards/VECTOR_SECURITY_GOVERNANCE.md) threat model; document mitigations and residual risk; file waivers for any unmet controls.
9. **Pilot in staging.** Route 5% of production traffic to the staging cluster; compare recall, latency, and safety metrics with the baseline.
10. **Promote to production.** Enable the production cluster; set the recall-budget alert and the safety-budget alert; hand off to the on-call rotation.
11. **Adopt the operating cadence.** Schedule the quarterly recall regression, the annual threat-model review, and the 180-day standard review.

## Rollback

1. Stop the embedding pipeline and freeze new writes to the collection.
2. Switch the workload back to the previous retrieval path (keyword search, prior collection, or prior store).
3. Quarantine the affected collection for forensic review; do not delete until the security review is complete.
4. Open a remediation ticket that captures the recall regression, the safety regression, or the security finding.
5. Communicate the rollback to stakeholders via the standard incident communication channel.
6. Update the workload specification with the lessons learned before the next adoption attempt.

## References

- [Vector Retrieval Governance](../standards/VECTOR_RETRIEVAL_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](../standards/VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [Vector Security Governance](../standards/VECTOR_SECURITY_GOVERNANCE.md)
- [Milvus Vector Database Version Governance](../reference/MILVUS_VERSION_GOVERNANCE.md)
- [Qdrant Vector Search Version Governance](../reference/QDRANT_VERSION_GOVERNANCE.md)
- [pgvector Version Governance](../reference/PGVECTOR_VERSION_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](../standards/OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
