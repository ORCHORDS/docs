---
title: Neo4j Graph Database Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://neo4j.com/release-notes/
---

# Neo4j Graph Database Version Governance

## Why this card exists

Neo4j is the leading property-graph database used by OrchestrAI products that require highly connected traversals, Cypher query semantics, and strong tooling for graph data science and graph RAG. Neo4j releases combine the database kernel, the Cypher query language, the Bolt binary protocol, and the Browser / Bloom frontends. Each major version ships breaking changes in the Cypher grammar, the storage format, and the cluster topology contract. This card defines how OrchestrAI selects, upgrades, and retires Neo4j versions across self-hosted clusters, Neo4j AuraDB managed, and Neo4j AuraDS managed data science.

## Scope

Applies to Neo4j Community Edition, Neo4j Enterprise Edition, Neo4j AuraDB, Neo4j AuraDS, and the official Neo4j drivers (Python, Java, JavaScript, Go, .NET). Excludes the Graph Data Science library (GDS), which is governed by its own version cadence pinned to the Neo4j server version.

## Versioning model

Neo4j follows `<major>.<minor>` for server releases (the patch level is implied by maintenance releases within a minor) and `<major>.<minor>.<patch>` for driver releases:

- **Major (server)** — incompatible storage format, breaking Cypher grammar, removal of a supported procedure, or breaking cluster topology contract.
- **Minor (server)** — backward-compatible feature additions (new indexes, new procedures, new Cypher constructs); storage format is forward-readable by the next major.
- **Patch (driver)** — bug fixes, security patches, performance backports; no protocol change.

Long-Term-Support releases are labelled `.<minor>.LTS` and receive patch backports for 18 months per the Neo4j support policy.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 5.26.x LTS | Primary | 2027-09 | Default for new clusters; introduces the new composite index GA and the vector index GA. |
| 5.25.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 5.20.x LTS | End of life | 2026-04 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 5.20 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest LTS minor (currently 5.26.x LTS).
2. The pin is recorded in the cluster manifest and validated by the platform reconciliation loop.
3. Workloads that depend on legacy Cypher constructs may pin to the 5.20.x LTS line until the LTS window closes.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor (LTS)** — applied within 90 days.
- **Minor (non-LTS)** — applied within 180 days, after running the cross-version Cypher regression suite and the database migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises database export / import, index rebuild, and cluster topology migration.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new databases cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| Neo4j Python driver | 5.25.x, 5.26.x | Driver minor must be compatible with server minor. |
| Neo4j Java driver | 5.25.x, 5.26.x | Driver minor must be compatible with server minor. |
| Bolt protocol | 5.x | Pinned by the driver. |
| Graph Data Science library | 2.13.x, 2.14.x | GDS minor must be compatible with server minor. |
| Apache Kafka Connect | 5.5.x | Used by Neo4j Streams; see [Kafka KIP Version Governance](KAFKA_KIP_VERSION_GOVERNANCE.md). |
| Apache Spark connector | 5.5.x | Used by the Spark connector for graph analytics. |

## Security and compliance

- TLS 1.2+ is mandatory for all client, cluster, and Browser traffic.
- Native authentication backed by LDAP / Active Directory / OIDC is required; legacy username/password authentication on shared clusters is deprecated.
- Audit logging is wired through the standard log pipeline; query-level audit events must include `user`, `database`, `query_text_hash`, `parameters_hash`, `operation`, and `execution_time_ms`.
- Personal data in graph nodes and relationships is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Query traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for query latency, transaction throughput, and cluster heartbeat live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Amazon Neptune Graph Database Version Governance](NEPTUNE_VERSION_GOVERNANCE.md)
- [Memgraph In-Memory Graph Database Version Governance](MEMGRAPH_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
