---
title: Amazon Neptune Graph Database Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://docs.aws.amazon.com/neptune/latest/userguide/release-notes.html
---

# Amazon Neptune Graph Database Version Governance

## Why this card exists

Amazon Neptune is the AWS managed graph database used by OrchestrAI products that require a fully managed property-graph or RDF triple-store with VPC-native networking and IAM-based authentication. Neptune releases combine the database engine, the SPARQL / openCypher / Gremlin query languages, and the cluster endpoint. Each engine version ships breaking changes in the query-language feature set, the storage format, and the cluster-replica contract. This card defines how OrchestrAI selects, upgrades, and retires Neptune engine versions across AWS regions.

## Scope

Applies to Neptune clusters (property-graph mode and RDF mode) and the Neptune Workbench / Jupyter integration. Excludes Neptune Serverless and Neptune Analytics, which are governed by their own AWS-managed release cadence.

## Versioning model

Neptune follows `<engine_major>.<engine_minor>`:

- **Engine major** — incompatible storage format, breaking query-language grammar, or removal of a supported query language (SPARQL, openCypher, Gremlin).
- **Engine minor** — backward-compatible feature additions (new query functions, new index types, new bulk-loader improvements); storage format is forward-readable by the next major.

Neptune supports two upgrade paths: in-place engine-version upgrade (for backward-compatible upgrades within a major) and snapshot-restore upgrade (for major version upgrades or rollbacks).

## Supported versions

| Engine version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 1.4.x | Primary | 2027-06 | Default for new clusters; introduces the openCypher 5 improvements and the new bulk loader GA. |
| 1.3.x | Maintenance | 2026-12 | Receives security patches; recommended upgrade path. |
| 1.2.x | End of life | 2026-06 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 1.2 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest stable engine minor (currently 1.4.x).
2. The pin is recorded in the cluster manifest and validated by the platform reconciliation loop.
3. Workloads that depend on legacy SPARQL features may pin to the 1.3.x line until the maintenance window closes.

## Upgrade cadence

- **Engine minor** — applied within 90 days of AWS general availability.
- **Engine major** — applied within 180 days; gated by a staging rehearsal that exercises snapshot-restore, query-language parity, and cluster-replica promotion.
- **AWS-managed maintenance** — applied within the AWS maintenance window; coordinated with the workload owner's freeze calendar.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date AWS announces end of support.
2. Clusters on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new databases cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| openCypher | 5 (Neptune 1.4+) | Property-graph query language. |
| SPARQL | 1.1 | RDF query language. |
| Gremlin | 3.4.x | Apache TinkerPop graph traversal language. |
| JDBC / ODBC drivers | latest | Used for BI integration. |
| Bulk loader | matches engine minor | Used for initial population and bulk updates. |
| Neptune Streams | enabled per cluster | Used for change-data-capture. |

## Security and compliance

- TLS 1.2+ is mandatory for all client and cluster traffic.
- IAM database authentication is the default; legacy username/password authentication is deprecated.
- VPC-native deployment is required; public endpoints are prohibited.
- Audit logging is wired through the standard log pipeline; query-level audit events must include `user`, `database`, `query_language`, `query_text_hash`, and `operation`.
- Personal data in graph nodes and relationships is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- CloudWatch metrics are scraped and forwarded to Prometheus; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Query traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for query latency, transaction throughput, and replica lag live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Neo4j Graph Database Version Governance](NEO4J_VERSION_GOVERNANCE.md)
- [Memgraph In-Memory Graph Database Version Governance](MEMGRAPH_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-145 Cloud Governance](../standards/NIST_SP_800_145_CLOUD_GOVERNANCE.md)
- [FedRAMP Rev. 5 MOD Governance](../standards/FEDRAMP_REV_5_MOD_GOVERNANCE.md)
