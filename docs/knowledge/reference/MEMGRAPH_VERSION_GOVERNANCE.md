---
title: Memgraph In-Memory Graph Database Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/memgraph/memgraph/releases
---

# Memgraph In-Memory Graph Database Version Governance

## Why this card exists

Memgraph is the in-memory, C++-implemented graph database used by OrchestrAI products that require high-throughput transactional graph workloads, real-time analytics, and dynamic graph algorithms. Memgraph releases combine the database kernel, the openCypher query language, the MAGE graph algorithms library, and the Lab / mgconsole frontends. Each major version ships breaking changes in the openCypher grammar, the storage engine configuration, and the replication contract. This card defines how OrchestrAI selects, upgrades, and retires Memgraph versions across self-hosted clusters and Memgraph Cloud.

## Scope

Applies to Memgraph Community, Memgraph Enterprise, Memgraph Cloud, the Memgraph Python driver (pymgclient / neo4j-python-driver compatibility), and the MAGE graph algorithms library. Excludes the underlying Linux distributions which are governed by their own cards.

## Versioning model

Memgraph follows `<major>.<minor>.<patch>`:

- **Major** — incompatible storage engine configuration, breaking openCypher grammar, removal of a supported procedure, or breaking replication contract.
- **Minor** — backward-compatible feature additions (new query procedures, new MAGE algorithms, new storage configuration options); storage engine configuration is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 3.3.x | Primary | 2027-03 | Default for new clusters; introduces the new storage mode (`IN_MEMORY_TRANSACTIONAL` GA) and the new dynamic sampling procedures. |
| 3.2.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 3.1.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 3.1 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest stable minor in the 3.3.x line.
2. The pin is recorded in the cluster manifest and validated by the platform reconciliation loop.
3. Pre-release builds are restricted to evaluation clusters and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version openCypher regression suite and the storage configuration migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises snapshot / restore, index rebuild, and replication topology migration.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new databases cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| Memgraph Python driver (`pymgclient`) | 1.4.x, 1.5.x | Driver minor must be compatible with server minor. |
| Memgraph Go driver (`mgclient`) | 1.4.x, 1.5.x | Driver minor must be compatible with server minor. |
| Bolt protocol | 5.x | Used for client-server communication. |
| MAGE library | matches server version | Graph algorithms library bundled with the server. |
| Memgraph Lab | latest minor | Frontend for query, visualization, and procedure browsing. |
| Kafka Streams connector | matches server version | Used for change-data-capture. |

## Security and compliance

- TLS 1.2+ is mandatory for all client, cluster, and Lab traffic.
- Native authentication backed by LDAP / OIDC is required; legacy username/password authentication on shared clusters is deprecated.
- Audit logging is wired through the standard log pipeline; query-level audit events must include `user`, `database`, `query_text_hash`, `parameters_hash`, `operation`, and `execution_time_ms`.
- Personal data in graph nodes and relationships is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Query traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for query latency, transaction throughput, and replication lag live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Neo4j Graph Database Version Governance](NEO4J_VERSION_GOVERNANCE.md)
- [Amazon Neptune Graph Database Version Governance](NEPTUNE_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
