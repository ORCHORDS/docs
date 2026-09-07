---
title: Qdrant Vector Search Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/qdrant/qdrant/releases
---

# Qdrant Vector Search Version Governance

## Why this card exists

Qdrant is a Rust-implemented vector search engine used by OrchestrAI products that require single-node simplicity, sub-millisecond latency on filtered hybrid retrieval, or in-memory payload indexing for compliance-bound workloads. Qdrant ships quarterly minor releases and occasional storage-format upgrades. This card defines how OrchestrAI selects, upgrades, and retires Qdrant versions across self-hosted clusters and Qdrant Cloud.

## Scope

Applies to Qdrant stand-alone, Qdrant cluster mode, and Qdrant Cloud managed instances. Excludes the Python and Rust client SDKs, which are pinned independently and validated against the server version.

## Versioning model

Qdrant follows `<major>.<minor>.<patch>`:

- **Major** — incompatible payload schema or wire protocol change; requires client SDK upgrade.
- **Minor** — backward-compatible feature additions (new index types, new filter expressions, sparse-vector support extensions); storage format is forward-readable by the next major.
- **Patch** — bug fixes, security backports, performance improvements.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 1.13.x | Primary | 2027-01 | Default for new clusters; introduces multivector blocks and improved quantization. |
| 1.12.x | Maintenance | 2026-06 | Receives security patches; recommended upgrade path. |
| 1.11.x | End of life | 2025-11 | Unsupported; migration to 1.12+ required. |
| < 1.11 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest stable minor in the 1.13.x line.
2. The pinning is recorded in the cluster manifest and validated by the platform reconciliation loop.
3. Pre-release builds (`-rc.N`) are restricted to evaluation clusters and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version recall regression suite.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises snapshot/restore, filtered retrieval, and payload index migration.

## Deprecation process

1. Deprecation is recorded against the cluster inventory on the day upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but lose eligibility for new feature rollouts.
3. The cluster policy controller blocks new collection creation on unsupported versions; reads continue until the next maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| qdrant-client Python | 1.12.x, 1.13.x | Pin to the matching minor. |
| qdrant-client Rust | 1.12.x, 1.13.x | Pin to the matching minor. |
| gRPC | 1.65+ | Internal protocol version validated at startup. |
| TLS | 1.2 / 1.3 | Required for all client and cluster traffic. |
| Snapshot storage | S3, GCS, MinIO | Object lock enabled for immutable snapshot retention (see [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md)). |

## Security and compliance

- API key authentication is mandatory; legacy JWT support is deprecated.
- Collection-level access control uses Qdrant 1.10+ keys and must align with the central RBAC.
- Payload-level audit events are routed through the standard audit pipeline; see [Audit Storage Capacity Review](../playbooks/AUDIT_STORAGE_CAPACITY_REVIEW.md) for retention and capacity rules.

## Observability

- Prometheus metrics are exposed on `:6333/metrics`; alerting rules follow the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- OTLP traces from the search and update paths feed the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for recall drift and tail latency live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Milvus Vector Database Version Governance](MILVUS_VERSION_GOVERNANCE.md)
- [pgvector Version Governance](PGVECTOR_VERSION_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](../standards/OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
