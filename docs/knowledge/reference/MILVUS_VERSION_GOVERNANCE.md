---
title: Milvus Vector Database Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://milvus.io/docs/release_notes.md
---

# Milvus Vector Database Version Governance

## Why this card exists

Milvus is the primary cloud-native vector database for very-large-scale retrieval-augmented generation (RAG), semantic search, and recommender workloads. Milvus releases major versions frequently (2.x line through 2025, 2.6 in late 2025) and each major release ships storage-format changes, query-optimizer rewrites, and index-engine replacements that affect data migration paths, recall/latency behaviour, and SDK compatibility. This card defines how OrchestrAI selects, upgrades, and retires Milvus versions.

## Scope

Applies to self-hosted Milvus clusters, Milvus stand-alone deployments (Milvus Lite), and Zilliz Cloud managed instances used by OrchestrAI products. Excludes Milvus-related but separate projects such as Attu (admin UI) and Milvus-CDC, which are covered by their own version-governance cards.

## Versioning model

Milvus follows `<major>.<minor>.<patch>` semantics:

- **Major** — incompatible storage format, breaking query-result or SDK contract, or removal of a supported index engine.
- **Minor** — backward-compatible feature additions (new index types, new SDK methods, new query expressions) and incremental storage format versions readable by the next major.
- **Patch** — bug fixes, performance backports, security patches; no schema change.

Long-Term-Support releases are labelled `.<minor>.LTS` (e.g. `2.6.0-LTS`) and receive patch backports for 12 months.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 2.6.x LTS | Primary | 2027-09 | Default for new clusters; supports GPU index (CAGRA), sparse + dense hybrid retrieval, and RBAC v2. |
| 2.5.x | Maintenance | 2026-06 | Receives security patches only; upgrade recommended. |
| 2.4.x | End of life | 2025-12 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 2.4 | End of life | — | Not permitted in production; assessed as a finding by the internal audit. |

## Selection criteria

1. New clusters default to the latest LTS minor (currently 2.6.x).
2. Pinned versions are recorded in the cluster manifest and validated by the platform reconciliation loop.
3. A change to a non-LTS minor is allowed for evaluation clusters only and must be re-evaluated every 90 days.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release; waived only for changes that fail the platform regression suite.
- **Minor (LTS)** — applied within 90 days; coordinated with the embedding-model registry so index parameters and vector dimensions stay aligned.
- **Major / non-LTS minor** — applied within 180 days, gated by a rehearsal migration in the staging environment that exercises schema upgrade, index rebuild, and rollback to the prior storage snapshot.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new collections cannot be created on unsupported versions, and read traffic is allowed until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| pymilvus SDK | 2.5.x, 2.6.x | SDK major version must match server major version. |
| Attu admin UI | latest minor of the same major | Pin via Helm chart. |
| etcd (metadata) | 3.5.x | Required for 2.5+; 3.4 unsupported. |
| MinIO / S3 (object storage) | MinIO RELEASE.2024-x or AWS S3 | Bucket lifecycle policies must permit the storage-format compaction jobs. |
| Kafka (log subscriber) | 3.5.x, 3.6.x | Used by Milvus-CDC and message-pack channels. |
| GPU index engine | CUDA 12.x with driver ≥ 535 | Required for CAGRA index. |

## Security and compliance

- TLS for client, internal-node, and etcd traffic is mandatory.
- RBAC v2 is required for multi-tenant clusters; legacy username/password authentication is deprecated.
- Audit logging is wired through the standard log pipeline; collection-level audit events must include `collection_name`, `actor`, `operation`, `vector_count`, and `query_expression_hash`.
- Vector data containing personal data is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on `:9091/health`; the alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Traces from proxy, mixcoord, and querynode are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for the vector index lag, recall estimator, and recall-budget alert live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Qdrant Vector Search Version Governance](QDRANT_VERSION_GOVERNANCE.md)
- [pgvector Version Governance](PGVECTOR_VERSION_GOVERNANCE.md)
- [Prometheus Monitoring System Version Governance](PROMETHEUS_VERSION_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](../standards/OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
