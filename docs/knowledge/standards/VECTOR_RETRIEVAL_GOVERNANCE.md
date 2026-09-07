# Vector Retrieval Governance

## 1. Scope

Govern the production use of vector retrieval systems (Milvus, Qdrant, pgvector, and managed equivalents) across OrchestrAI products. Covers indexing, query semantics, recall budgets, tenant isolation, and observability requirements. Applies to retrieval-augmented generation (RAG), semantic search, recommendation, and duplicate-detection workloads.

Excludes pure keyword search and exact-match systems, which are governed separately. Excludes vector embedding model selection, which is governed by [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md).

## 2. Normative references

- [Milvus Vector Database Version Governance](../reference/MILVUS_VERSION_GOVERNANCE.md)
- [Qdrant Vector Search Version Governance](../reference/QDRANT_VERSION_GOVERNANCE.md)
- [pgvector Version Governance](../reference/PGVECTOR_VERSION_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)

## 3. Terms and definitions

- **Vector index** — the on-disk and in-memory data structure used for approximate nearest neighbour (ANN) retrieval.
- **Recall budget** — the minimum acceptable recall@K that a workload must sustain over a representative evaluation set.
- **Hybrid retrieval** — combination of dense vector similarity with sparse or keyword scoring.
- **Tenant scope** — a logical partition that constrains vector reads and writes to a single tenant.

## 4. Index selection

1. New collections must select HNSW by default unless the dataset exceeds 50 million vectors, in which case IVF or DiskANN is permitted.
2. Index parameters (`ef_construction`, `M`, `nlist`, `nprobe`) are pinned in the collection manifest; runtime override is prohibited without a change ticket.
3. Quantization (SQ8, binary, halfvec) is permitted only when the recall budget is documented in the collection manifest and validated against the evaluation set at least every 90 days.
4. Re-indexing is triggered when the live recall estimate drops below the declared recall budget for more than 24 hours.

## 5. Query semantics

1. All production queries must declare an explicit top-K, a distance metric, and an optional filter expression.
2. Hybrid retrieval must persist both the dense and sparse scores; the final ranking is the weighted sum declared in the workload specification.
3. Result post-processing (re-ranking, deduplication, threshold filtering) is versioned in the workload spec and reproducible from a recorded seed.
4. Vector queries must enforce tenant scoping via a mandatory payload filter; queries without a tenant filter are rejected by the access layer.

## 6. Recall and quality assurance

1. Every production collection ships with a representative evaluation set of at least 1,000 queries drawn from production traffic or seeded by the workload owner.
2. Recall@K is measured weekly against the evaluation set; results are stored for 12 months.
3. A drop of more than 2 percentage points relative to the baseline triggers the recall-budget alert and opens a remediation ticket.
4. The recall budget is declared per workload and recorded in the workload specification; default budget is 0.95 recall@10 for retrieval workloads.

## 7. Tenant isolation and access control

1. Multi-tenant collections must use row-level or collection-level scoping enforced at the access layer, never in application code alone.
2. API keys are scoped per workload and rotated at least every 90 days.
3. Cross-tenant queries are prohibited; the access layer rejects any query whose tenant filter does not match the caller's identity.
4. The tenant boundary is audited quarterly; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).

## 8. Data lifecycle

1. Vector embeddings derived from personal data are subject to the same retention and deletion rules as the source record.
2. Embedding deletion is propagated to all vector stores via the standard data-lifecycle pipeline; the deletion event is recorded in the audit log.
3. Vector backups use immutable object storage; see [NIST SP 800-189 Immutable Storage Governance](NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
4. Re-embedding due to model upgrade is treated as a controlled migration; old embeddings are quarantined until the migration is verified.

## 9. Security

1. TLS 1.2+ is required for all client and inter-node traffic.
2. API keys and passwords are stored in the central secret manager; embedding pipelines never embed secrets in payloads.
3. Embeddings that encode personal data are encrypted at rest; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
4. LLM-specific threats (prompt injection, embedding inversion, retrieval leakage) are tracked under [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md).

## 10. Observability

1. Vector retrieval emits Prometheus metrics for QPS, p50/p95/p99 latency, recall estimator, and index build lag.
2. Retrieval requests are traced via OTLP and include `collection`, `query_hash`, `tenant`, `top_k`, and `result_count`.
3. SLOs are defined per workload using the standard SLO template; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
4. Dashboards and alerts are owned by the workload owner; see [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md) and [Prometheus Alerting Adoption Playbook](../playbooks/PROMETHEUS_ALERTING_ADOPTION_PLAYBOOK.md).

## 11. Operating model

1. The Vector Platform team owns the shared infrastructure (Milvus clusters, Qdrant clusters, pgvector extension) and the reference configurations.
2. Workload owners own the collection schema, evaluation set, and recall budget.
3. Security reviews are required for new tenants, new workloads processing sensitive data, and any change to the embedding pipeline.
4. The Vector Platform guild meets monthly to review recall regressions, capacity, and adoption of new index types.

## 12. Exceptions

Exceptions to this standard require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
