# Time-Series Database Architecture Governance

## 1. Scope

Govern the architecture, selection, and operational use of time-series databases (TimescaleDB, InfluxDB, QuestDB, and managed equivalents) across OrchestrAI products. Covers ingest pipeline selection, schema design for time-series tables / hypertables / buckets, partitioning, downsampling, and integration with observability, feature, and vector subsystems.

Excludes the underlying compute and storage engines (PostgreSQL, object storage) which are governed by their own cards. Excludes retention and compression, which are governed by [Time-Series Retention & Compression Governance](TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md). Excludes query performance, which is governed by [Time-Series Query Performance Governance](TIME_SERIES_QUERY_PERFORMANCE_GOVERNANCE.md).

## 2. Normative references

- [TimescaleDB Time-Series Database Version Governance](../reference/TIMESCALEDB_VERSION_GOVERNANCE.md)
- [InfluxDB Time-Series Platform Version Governance](../reference/INFLUXDB_VERSION_GOVERNANCE.md)
- [QuestDB Time-Series Database Version Governance](../reference/QUESTDB_VERSION_GOVERNANCE.md)
- [PostgreSQL Version Governance](../reference/POSTGRES_VERSION_GOVERNANCE.md)
- [Time-Series Retention & Compression Governance](TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md)
- [Time-Series Query Performance Governance](TIME_SERIES_QUERY_PERFORMANCE_GOVERNANCE.md)
- [Prometheus Monitoring System Version Governance](../reference/PROMETHEUS_VERSION_GOVERNANCE.md)
- [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md)
- [OpenTelemetry Collector Contrib Version Governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)

## 3. Terms and definitions

- **Time-series table** — a table whose primary key includes a timestamp column and which is optimised for high-volume append and bounded retention.
- **Hypertable** — the TimescaleDB abstraction that automatically partitions a time-series table into chunks.
- **Bucket** — the InfluxDB v3 unit of organisation for a set of time-series data, with its own retention policy.
- **Continuous aggregate** — a TimescaleDB materialized view that is incrementally maintained as new data arrives.
- **Downsampling task** — an InfluxDB or QuestDB scheduled operation that rolls up raw data into coarser-grained aggregates.
- **Tag / label** — a low-cardinality indexed dimension that is part of the time-series identity.
- **Field** — a high-cardinality numeric or string value associated with a timestamp and a set of tags.

## 4. Time-series database selection

1. TimescaleDB is the default time-series database for products that need co-location with relational metadata, transactional updates, or row-level security.
2. InfluxDB is preferred for products that require very high ingest throughput, native downsampling, and integrated tasks / dashboards.
3. QuestDB is preferred for products that require extremely low-latency SQL queries on high-ingest workloads (tick data, IoT telemetry, financial market data).
4. The choice is recorded in the time-series manifest and reviewed annually.

## 5. Schema contract

1. Every time-series table declares its measurement name, tag set, field set, retention policy, compression policy, partitioning interval, and AI risk tier.
2. Schema versions are immutable; breaking changes require a new schema major version and a migration plan.
3. Backwards-compatible additions (new tags, new fields) are permitted under a new schema minor version.
4. Deprecated schema elements remain readable for at least 180 days after deprecation; the deprecation date and the migration target are recorded in the manifest.

## 6. Tag and field design

1. Tags are low-cardinality indexed dimensions (typically ≤ 10,000 distinct values per tag); high-cardinality values are stored as fields.
2. The tag set is the time-series identity; changing the tag set creates a new series.
3. Field types are declared at schema creation time and may not change at write time.
4. Tag and field naming follows a documented convention enforced by the schema linter.

## 7. Partitioning and chunking

1. Hypertable chunks and InfluxDB / QuestDB partitions are sized to allow efficient compression and bounded query windows.
2. Chunk / partition intervals are recorded in the manifest; runtime override is prohibited without a change ticket.
3. Chunk / partition bloat is monitored and remediated at least every 90 days.
4. New chunks / partitions are validated against the representative query set at adoption time.

## 8. Ingest pipeline selection

1. Ingest pipelines use the database's native ingest protocol (TimescaleDB SQL, InfluxDB line protocol, QuestDB ILP) when available.
2. Ingest agents (Telegraf, vector, custom collectors) are pinned per workload and recorded in the manifest.
3. Backpressure is enforced at the ingest agent; the database rejects writes above the configured ceiling.
4. Ingest rate, lag, and error rate are wired to the standard SLO set; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).

## 9. Integration with downstream subsystems

1. Continuous aggregates that feed the feature store must follow [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md) for lineage emission.
2. Continuous aggregates that feed the vector store must follow [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md) for lineage emission.
3. Continuous aggregates consumed by regulated models must satisfy the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Cross-subsystem integration is wired through the time-series manifest and validated at adoption time.

## 10. Reliability and observability

1. Workloads must declare an expected query-latency SLO and an expected availability SLO; chronic breaches trigger a schema-contract review.
2. Time-series query events are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
3. SLOs are defined per workload using the standard SLO template; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
4. Dashboards and alerts are owned by the workload owner; see [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md) and [Prometheus Alerting Adoption Playbook](../playbooks/PROMETHEUS_ALERTING_ADOPTION_PLAYBOOK.md).

## 11. Security

1. TLS is required for all client and cluster traffic.
2. Access to time-series data is gated by RBAC; legacy single-user access is deprecated.
3. Personal data in time-series values is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Retention and compression controls are governed by [Time-Series Retention & Compression Governance](TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md).

## 12. Operating model

1. The Time-Series Platform team owns the shared time-series infrastructure and the reference schema templates.
2. Workload owners own their schemas, queries, and runtime SLOs.
3. The Time-Series Platform guild meets monthly to review ingest latency regressions, query performance, and adoption of new time-series databases.
4. New time-series vendors are evaluated by the Time-Series Platform team and approved by the AI Governance Council.

## 13. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 14. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
