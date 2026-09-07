---
title: InfluxDB Time-Series Platform Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/influxdata/influxdb/releases
---

# InfluxDB Time-Series Platform Version Governance

## Why this card exists

InfluxDB is the purpose-built time-series platform used by OrchestrAI products that require high-ingest throughput, native downsampling, and integrated tasks / dashboards. The v3 release (powered by the IOx storage engine) replaced the v2 (TSM) engine with a columnar, Parquet-backed storage layer and a single SQL query surface (InfluxQL / Flux deprecated in favour of SQL). Each major version ships breaking changes in the query language, the storage engine, and the task / processing model. This card defines how OrchestrAI selects, upgrades, and retires InfluxDB versions across self-hosted deployments and InfluxDB Cloud (v3).

## Scope

Applies to InfluxDB OSS v3, InfluxDB Enterprise, and InfluxDB Cloud (v3). Excludes InfluxDB v1 / v2 deployments, which are end-of-life or in maintenance; legacy v1 / v2 clusters must be migrated to v3 before the next compliance renewal.

## Versioning model

InfluxDB follows `<major>.<minor>.<patch>`:

- **Major** — incompatible storage engine, breaking SQL dialect change, or removal of a supported ingest protocol (line protocol, telegraf, native HTTP).
- **Minor** — backward-compatible feature additions (new SQL functions, new task triggers, new processing operators); storage engine format is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 3.x | Primary | 2027-03 | Default for new deployments; columnar Parquet storage, native SQL, processing in Rust. |
| 2.7.x | Maintenance | 2026-09 | Receives security patches; migration to 3.x recommended for all new workloads. |
| 2.6.x | End of life | 2025-12 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| 1.x | End of life | — | Not permitted in production. |

## Selection criteria

1. New deployments default to InfluxDB 3.x.
2. The pin is recorded in the cluster manifest and validated by the platform reconciliation loop.
3. Pre-release builds are restricted to evaluation deployments and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version ingest regression suite and the storage engine migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises Parquet migration, task replay, and SQL dialect parity.
- **v2 → v3 migration** — applied within 365 days of v3 GA; coordinated with the workload owner's freeze calendar.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Deployments on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new buckets cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| InfluxDB CLI | matches server minor | Pinned via package manager. |
| Telegraf | 1.30+ | Default ingest agent; plugin compatibility declared per plugin. |
| InfluxDB HTTP API | v2 wire-compatible | Stable for v3 reads and writes; v1 API removed. |
| Grafana | latest minor | Standard visualization; uses the Flux / SQL datasource. |
| Prometheus remote-write | 3.x | Supported via the official receiver. |
| Apache Parquet | 1.13+ | Required for the columnar storage layer. |

## Security and compliance

- TLS 1.2+ is mandatory for all client and cluster traffic.
- OIDC-based authentication is required; legacy username/password authentication on shared clusters is deprecated.
- Audit logging is wired through the standard log pipeline; query-level audit events must include `database`, `measurement`, `actor`, `operation`, and `execution_time_ms`.
- Personal-data time-series values are in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Query and task traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for ingest rate, query latency, task backlog, and storage compression ratio live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [TimescaleDB Time-Series Database Version Governance](TIMESCALEDB_VERSION_GOVERNANCE.md)
- [QuestDB Time-Series Database Version Governance](QUESTDB_VERSION_GOVERNANCE.md)
- [Prometheus Monitoring System Version Governance](PROMETHEUS_VERSION_GOVERNANCE.md)
- [Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
