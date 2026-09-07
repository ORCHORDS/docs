---
title: QuestDB Time-Series Database Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/questdb/questdb/releases
---

# QuestDB Time-Series Database Version Governance

## Why this card exists

QuestDB is the Java / C++ implemented, column-oriented time-series database used by OrchestrAI products that require extremely low-latency SQL queries on high-ingest workloads (tick data, IoT telemetry, financial market data). QuestDB releases combine the database kernel, the SQL dialect with native time-series extensions, the InfluxDB line-protocol ingest endpoint, and the Web Console. Each major version ships breaking changes in the SQL dialect, the storage format, and the replication topology contract. This card defines how OrchestrAI selects, upgrades, and retires QuestDB versions across self-hosted clusters and QuestDB Cloud.

## Scope

Applies to QuestDB OSS, QuestDB Enterprise, QuestDB Cloud, and the official QuestDB Python / Go / Java / .NET clients. Excludes the underlying Linux distributions which are governed by their own cards.

## Versioning model

QuestDB follows `<major>.<minor>.<patch>`:

- **Major** — incompatible SQL dialect change, breaking storage format, or removal of a supported ingest protocol (InfluxDB line protocol, PostgreSQL wire protocol, ILP).
- **Minor** — backward-compatible feature additions (new SQL functions, new table types, new ingest protocol improvements); storage format is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 8.2.x | Primary | 2027-03 | Default for new clusters; introduces the new replication contract and the Web Console v3 GA. |
| 8.1.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 8.0.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 8.0 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest stable minor in the 8.2.x line.
2. The pin is recorded in the cluster manifest and validated by the platform reconciliation loop.
3. Pre-release builds are restricted to evaluation clusters and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version SQL regression suite and the storage format migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises snapshot / restore, table rebuild, and replication topology migration.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new tables cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| QuestDB Python client | 1.2.x, 1.3.x | Client minor must be compatible with server minor. |
| QuestDB Go client | 1.0.x | Pinned via go modules. |
| QuestDB PostgreSQL wire | 13+ | Supported for clients using the PostgreSQL protocol. |
| QuestDB InfluxDB line protocol | 1.x | Supported for clients using ILP. |
| Grafana | latest minor | Standard visualization; uses the PostgreSQL datasource. |
| Apache Kafka | 3.5.x, 3.6.x | Used by the Kafka connector for change-data-capture. |

## Security and compliance

- TLS 1.2+ is mandatory for all client and cluster traffic.
- OIDC-based authentication is required for shared clusters; legacy username/password authentication is deprecated.
- Audit logging is wired through the standard log pipeline; query-level audit events must include `database`, `table`, `actor`, `operation`, and `execution_time_ms`.
- Personal-data time-series values are in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Query and ingest traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for ingest rate, query latency, partition lag, and replication health live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [TimescaleDB Time-Series Database Version Governance](TIMESCALEDB_VERSION_GOVERNANCE.md)
- [InfluxDB Time-Series Platform Version Governance](INFLUXDB_VERSION_GOVERNANCE.md)
- [Prometheus Monitoring System Version Governance](PROMETHEUS_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
