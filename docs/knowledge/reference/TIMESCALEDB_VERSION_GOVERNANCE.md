---
title: TimescaleDB Time-Series Database Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/timescale/timescaledb/releases
---

# TimescaleDB Time-Series Database Version Governance

## Why this card exists

TimescaleDB is the PostgreSQL extension that provides automated partitioning, native compression, and continuous aggregates for time-series workloads. It is the preferred time-series store for OrchestrAI products that need to co-locate time-series data with relational metadata, transactional updates, or row-level security. TimescaleDB releases follow the PostgreSQL major-version cadence and introduce hypercore storage engines, tiered storage, and continuous-aggregate improvements. This card defines how OrchestrAI selects, upgrades, and retires TimescaleDB versions across managed PostgreSQL (Timescale Cloud, AWS RDS, Azure Database for PostgreSQL) and self-hosted clusters.

## Scope

Applies to all PostgreSQL instances running the TimescaleDB extension for OrchestrAI products. Excludes the upstream PostgreSQL version, which is governed by [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md). Excludes the Timescale Cloud control plane, which is governed by the vendor.

## Versioning model

TimescaleDB follows PostgreSQL's `<major>.<minor>` convention and aligns with the underlying PostgreSQL major version:

- **Major** — must match the PostgreSQL major version; introduces breaking changes in the hypercore storage engine or in the continuous-aggregate contract.
- **Minor** — backward-compatible additions (new hypercore features, new continuous-aggregate improvements, new compression algorithms); hypercore storage is forward-readable by the next major.

TimescaleDB also publishes an LTS designation (`<major>.<minor>.LTS`) for stable production deployments.

## Supported versions

| Version | Status | PostgreSQL major | Notes |
| --- | --- | --- | --- |
| 2.18.x LTS | Primary | 16, 17 | Default for new clusters; introduces the hypercore `vectorized_query` GA and the tiered-storage improvements. |
| 2.17.x | Maintenance | 16, 17 | Receives security patches; recommended upgrade path. |
| 2.16.x | End of life | 15, 16 | Unsupported; clusters must be migrated before compliance renewal. |
| < 2.16 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to TimescaleDB 2.18.x LTS on PostgreSQL 16 or 17.
2. The pin is recorded in the cluster manifest and reconciled daily by the platform reconciliation loop.
3. The choice between hypercore tiered storage and chunk-based storage is recorded per hypertable; tiered storage is the default for new hypertables.

## Upgrade cadence

- **Minor** — applied within 90 days, after a staging rehearsal that exercises extension upgrade, hypercore migration, and continuous-aggregate rebuild.
- **Major (PostgreSQL major)** — applied within 180 days, aligned with the PostgreSQL upgrade schedule and the standard [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md).
- **PostgreSQL minor** — coordinated with the upstream PostgreSQL minor release schedule.

## Deprecation process

1. Deprecation is recorded against the cluster inventory when upstream marks a minor end of life.
2. Clusters on deprecated versions continue to receive monitoring but lose eligibility for new feature rollouts.
3. The cluster policy controller blocks creation of new hypertables on unsupported versions; reads continue until the next maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| PostgreSQL | 14, 15, 16, 17 | Pin to a currently supported PostgreSQL major; see [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md). |
| TimescaleDB Toolkit | 2.18.x | Companion extension for analytics functions. |
| TimescaleDB Vector | 0.x | Companion extension for embedding storage; see [pgvector Version Governance](PGVECTOR_VERSION_GOVERNANCE.md). |
| Prometheus remote-write | 2.18.x | Supported via the `timescaledb-prometheus` adapter. |
| Grafana | latest minor | Standard visualization. |

## Security and compliance

- TLS is required for all client connections.
- Row-level security is enforced on every multi-tenant hypertable; tenant scoping is validated at insertion and query time.
- Audit logging is enabled via `pgaudit`; hypertable-level audit events include `hypertable_name`, `chunk_name`, `actor`, `operation`, and `compression_status`.
- Personal-data time-series values are in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- PostgreSQL metrics are scraped by Prometheus ([Prometheus Monitoring System Version Governance](PROMETHEUS_VERSION_GOVERNANCE.md)) using `postgres_exporter`; hypercore-specific metrics are exposed via the TimescaleDB metrics extension.
- Query-level traces from the time-series retrieval path are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for chunk count, compression ratio, continuous-aggregate lag, and tiered-storage traffic live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [InfluxDB Time-Series Platform Version Governance](INFLUXDB_VERSION_GOVERNANCE.md)
- [QuestDB Time-Series Database Version Governance](QUESTDB_VERSION_GOVERNANCE.md)
- [PostgreSQL Version Governance](POSTGRES_VERSION_GOVERNANCE.md)
- [Prometheus Monitoring System Version Governance](PROMETHEUS_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
