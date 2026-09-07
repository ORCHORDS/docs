---
title: pgvector Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md
---

# pgvector Version Governance

## Why this card exists

pgvector is the PostgreSQL extension that provides in-database vector storage, indexing, and similarity search. It is the preferred vector store when retrieval must co-locate with relational metadata, transactional updates, or row-level security. pgvector releases follow the PostgreSQL major-version cadence and add new index types (HNSW, IVF, hybrid), quantization (halfvec, bitvec), and parallel-scan improvements. This card defines how OrchestrAI selects, upgrades, and retires pgvector across managed PostgreSQL and self-hosted clusters.

## Scope

Applies to all PostgreSQL instances (managed and self-hosted) running the pgvector extension for OrchestrAI products. Excludes the upstream PostgreSQL version, which is governed by [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md).

## Versioning model

pgvector follows PostgreSQL's `<major>.<minor>` convention and aligns with the underlying PostgreSQL major version:

- **Major** — must match the PostgreSQL major version; introduces breaking changes in binary index format or SQL function signatures.
- **Minor** — backward-compatible additions (new index types, new distance operators, parallel-worker improvements).

## Supported versions

| Version | Status | PostgreSQL major | Notes |
| --- | --- | --- | --- |
| 0.8.x | Primary | 16, 17 | Default for new clusters; adds bitvec, sparsevec, and improved HNSW build parallelism. |
| 0.7.x | Maintenance | 14, 15, 16 | Receives security patches; recommended upgrade path. |
| 0.6.x | End of life | 13, 14, 15 | Unsupported; migration to 0.7+ required. |
| < 0.6 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to pgvector 0.8.x on PostgreSQL 16 or 17.
2. The pin is recorded in the cluster manifest and reconciled daily by the platform reconciliation loop.
3. The choice between HNSW and IVF index is recorded per collection; HNSW is the default for new collections up to 10 million vectors.

## Upgrade cadence

- **Minor** — applied within 90 days, after a staging rehearsal that exercises index rebuild, recall regression suite, and rollback via `pg_dump` snapshot.
- **Major (PostgreSQL major)** — applied within 180 days, aligned with the PostgreSQL upgrade schedule and the standard [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md).
- **PostgreSQL minor** — coordinated with the upstream PostgreSQL minor release schedule.

## Deprecation process

1. Deprecation is recorded against the cluster inventory when upstream marks a minor end of life.
2. Clusters on deprecated versions continue to receive monitoring but lose eligibility for new feature rollouts.
3. The cluster policy controller blocks creation of new vector indexes on unsupported versions; reads continue until the next maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| PostgreSQL | 14, 15, 16, 17 | Pin to a currently supported PostgreSQL major; see [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md). |
| psycopg / asyncpg | latest minor | Client drivers must support the binary vector codec. |
| pgvector-python | 0.3.x | Used for embedding-pipeline integration. |
| Disk-backed HNSW | PostgreSQL ≥ 14 | Required for datasets exceeding shared_buffers. |
| Row-level security | PostgreSQL ≥ 14 | Mandatory for multi-tenant vector tables. |

## Security and compliance

- TLS is required for all client connections.
- Row-level security is enforced on every multi-tenant vector table; tenant scoping is validated at insertion and query time.
- Audit logging is enabled via `pgaudit`; vector-specific events include `vector_insert`, `vector_query`, and `vector_index_rebuild`.
- Personal-data embeddings are in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- PostgreSQL metrics are scraped by Prometheus ([Prometheus Monitoring System Version Governance](PROMETHEUS_VERSION_GOVERNANCE.md)) using `postgres_exporter`.
- Query-level traces from the vector retrieval path are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for index size, recall budget, and parallel worker saturation live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Milvus Vector Database Version Governance](MILVUS_VERSION_GOVERNANCE.md)
- [Qdrant Vector Search Version Governance](QDRANT_VERSION_GOVERNANCE.md)
- [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](../standards/OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
