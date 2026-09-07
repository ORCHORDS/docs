# Time-Series Database Adoption Playbook

## Purpose

Adopt a time-series database (TimescaleDB, InfluxDB, QuestDB, or managed equivalent) for a new workload that requires high-volume metric ingest, bounded retention, and continuous aggregates or downsampled views. The playbook aligns with [Time-Series Database Architecture Governance](../standards/TIME_SERIES_DATABASE_ARCHITECTURE_GOVERNANCE.md), [Time-Series Retention & Compression Governance](../standards/TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md), and [Time-Series Query Performance Governance](../standards/TIME_SERIES_QUERY_PERFORMANCE_GOVERNANCE.md).

## Audience

Workload owners, Time-Series Platform engineers, observability engineers, security reviewers.

## Pre-conditions

1. The time-series database reference card is current (`TIMESCALEDB_VERSION_GOVERNANCE.md`, `INFLUXDB_VERSION_GOVERNANCE.md`, `QUESTDB_VERSION_GOVERNANCE.md`).
2. AI Impact Assessment is filed for the workload; see [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md).
3. Tenant scoping and data-classification decisions are documented.
4. Source datasets are registered in the catalogue with documented freshness and retention.
5. A representative query set is available or scheduled for capture.

## Procedure

1. **Select the time-series database.** Choose TimescaleDB for co-location with relational metadata; choose InfluxDB for high ingest throughput and integrated tasks / dashboards; choose QuestDB for extremely low-latency SQL on high-ingest workloads.
2. **Provision the cluster.** Apply the platform Helm chart or Terraform module pinned to the supported minor; record the cluster manifest in the inventory.
3. **Configure authentication and authorization.** Provision workload-scoped service-account credentials in the central secret backend; enable OIDC for interactive users; disable legacy username/password authentication.
4. **Design the schema.** Declare measurement name, tag set, field set, retention policy, compression policy, partitioning interval, and AI risk tier. Validate low tag cardinality and explicit field types.
5. **Configure ingest pipelines.** Wire Telegraf, vector, or custom collectors to the native ingest protocol; declare the backpressure ceiling and the ingest agent version in the manifest.
6. **Configure compression and tiered storage.** Declare compression segment-by, order-by, and compression_after thresholds; declare the tier migration window.
7. **Configure continuous aggregates or downsampling tasks.** Declare the schedule, the refresh window, and the lag alert thresholds.
8. **Wire lineage.** Emit lineage records with every write; reject writes without a complete lineage record.
9. **Validate query safety and performance.** Run the representative query set against the staging cluster; verify time-range limits, high-cardinality tag rejection, tenant scoping, and index usage.
10. **Wire observability.** Enable Prometheus metrics, OTLP traces, query-latency SLO dashboards, continuous-aggregate lag alerts, and tenant-scope alerts following the standard observability requirements.
11. **Run a security review.** Walk through the [Time-Series Query Performance Governance](../standards/TIME_SERIES_QUERY_PERFORMANCE_GOVERNANCE.md) threat model; document mitigations and residual risk; file waivers for any unmet controls.
12. **Pilot in staging.** Route 5% of production traffic to the staging cluster; compare ingest rate, query latency, compression ratio, and tenant scoping with the baseline.
13. **Promote to production.** Enable the production cluster; set the query-latency SLO alert, the continuous-aggregate lag alert, the tenant-scope alert, and the retention / compression alert; hand off to the on-call rotation.
14. **Adopt the operating cadence.** Schedule the quarterly query-plan regression, the annual threat-model review, the 90-day capacity forecast, and the 180-day standard review.

## Rollback

1. Stop the ingest pipelines and freeze new writes.
2. Switch the workload back to the previous time-series source (Prometheus, prior database, or pre-computed table).
3. Quarantine the schema for forensic review; do not delete until the security review is complete.
4. Open a remediation ticket that captures the query latency regression, the tenant-scope breach, the compression-ratio regression, or the security finding.
5. Communicate the rollback to stakeholders via the standard incident communication channel.
6. Update the workload specification with the lessons learned before the next adoption attempt.

## References

- [Time-Series Database Architecture Governance](../standards/TIME_SERIES_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Time-Series Retention & Compression Governance](../standards/TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md)
- [Time-Series Query Performance Governance](../standards/TIME_SERIES_QUERY_PERFORMANCE_GOVERNANCE.md)
- [TimescaleDB Time-Series Database Version Governance](../reference/TIMESCALEDB_VERSION_GOVERNANCE.md)
- [InfluxDB Time-Series Platform Version Governance](../reference/INFLUXDB_VERSION_GOVERNANCE.md)
- [QuestDB Time-Series Database Version Governance](../reference/QUESTDB_VERSION_GOVERNANCE.md)
- [PostgreSQL Version Governance](../reference/POSTGRES_VERSION_GOVERNANCE.md)
- [Prometheus Monitoring System Version Governance](../reference/PROMETHEUS_VERSION_GOVERNANCE.md)
- [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
