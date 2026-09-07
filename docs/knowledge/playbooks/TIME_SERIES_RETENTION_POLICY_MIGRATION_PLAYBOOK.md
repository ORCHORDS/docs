# Time-Series Retention Policy Migration Playbook

## Purpose

Migrate an existing time-series workload (TimescaleDB, InfluxDB, QuestDB) to a new retention policy, compression policy, or tiered-storage configuration while preserving the workload's query-latency SLO, lineage integrity, and tenant-scoping guarantees. The playbook aligns with [Time-Series Retention & Compression Governance](../standards/TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md) and [Time-Series Database Architecture Governance](../standards/TIME_SERIES_DATABASE_ARCHITECTURE_GOVERNANCE.md).

## Audience

Workload owners, Time-Series Platform engineers, observability engineers, AI Governance Council reviewers.

## Pre-conditions

1. The target retention / compression / tiered-storage configuration is documented in the time-series manifest.
2. The target archival destination (object storage) is provisioned with the required retention and encryption posture; see [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
3. The query-latency SLO and the lineage contract for the workload are documented; the evaluation query set is current.
4. A staging replica of the source time-series data is available for the rehearsal run.
5. Security review is complete for any change that affects personal-data retention.

## Procedure

1. **Scope the migration.** Identify the source and target retention / compression / tiered-storage configuration, the cutover strategy (gradual with overlap, or shadow with cutover), the batch size, and the abort criteria. Record the plan in the migration ticket.
2. **Rehearse in staging.** Apply the target configuration to the staging cluster; replay representative ingest and query traffic; measure ingest rate, query latency, compression ratio, and tenant scoping against the existing configuration. Resolve any regression before the production run.
3. **Validate archival and deletion.** For retention reductions, validate that the archival pipeline correctly exports older data to the immutable object store before deletion; verify the data is restorable from the archive.
4. **Validate compression and tier migration.** For compression or tiered-storage changes, validate that chunks / partitions transition to the new state on the declared schedule and that queries transparently read from the new state.
5. **Apply the configuration to production.** Configure the production cluster with the target retention / compression / tiered-storage configuration; validate that the database's native scheduler accepts the change.
6. **Validate during the migration.** Sample at least 100 chunks / partitions and compare ingest rate, query latency, compression ratio, and tenant scoping against the baseline. Halt the migration if any metric regresses by more than the abort criterion.
7. **Validate archival completeness.** After the migration window, validate that the archival pipeline has captured all data that fell outside the new retention window and that the archive is restorable.
8. **Sign off.** Confirm the query-latency SLO is met, lineage records are complete, compression ratio is within the declared minimum, and archival is complete; close the migration ticket.
9. **Decommission the previous configuration.** After the validation window, remove the previous retention / compression / tiered-storage configuration following the data-lifecycle procedure.

## Rollback

1. Stop the migration and freeze the configuration changes.
2. Revert the production cluster to the previous retention / compression / tiered-storage configuration.
3. If archival has already deleted data, restore from the most recent archive; document the data gap.
4. Open a remediation ticket that captures the regression metric, the abort criterion that was triggered, and the proposed fix.
5. Communicate the rollback to stakeholders and reschedule the migration after the fix is verified.

## References

- [Time-Series Retention & Compression Governance](../standards/TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md)
- [Time-Series Database Architecture Governance](../standards/TIME_SERIES_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Time-Series Query Performance Governance](../standards/TIME_SERIES_QUERY_PERFORMANCE_GOVERNANCE.md)
- [TimescaleDB Time-Series Database Version Governance](../reference/TIMESCALEDB_VERSION_GOVERNANCE.md)
- [InfluxDB Time-Series Platform Version Governance](../reference/INFLUXDB_VERSION_GOVERNANCE.md)
- [QuestDB Time-Series Database Version Governance](../reference/QUESTDB_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md)
- [Backup Coverage Review](BACKUP_COVERAGE_REVIEW.md)
- [Encryption Coverage Review](ENCRYPTION_COVERAGE_REVIEW.md)
