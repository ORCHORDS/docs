# Time-Series Retention & Compression Governance

## 1. Scope

Govern the retention, compression, tiered storage, and archival posture of time-series databases (TimescaleDB, InfluxDB, QuestDB, and equivalents) across OrchestrAI products. Covers retention policy declaration, compression algorithm selection, tiered storage configuration, archival and deletion procedures, and capacity planning.

Excludes time-series schema design, which is governed by [Time-Series Database Architecture Governance](TIME_SERIES_DATABASE_ARCHITECTURE_GOVERNANCE.md). Excludes query performance, which is governed by [Time-Series Query Performance Governance](TIME_SERIES_QUERY_PERFORMANCE_GOVERNANCE.md). Excludes general retention and archival governance, which is governed by [ISO/IEC 27040:2015 Storage Security Governance](ISO_IEC_27040_2015_STORAGE_SECURITY_GOVERNANCE.md) and [NIST SP 800-189 Immutable Storage Governance](NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).

## 2. Normative references

- [Time-Series Database Architecture Governance](TIME_SERIES_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Time-Series Query Performance Governance](TIME_SERIES_QUERY_PERFORMANCE_GOVERNANCE.md)
- [TimescaleDB Time-Series Database Version Governance](../reference/TIMESCALEDB_VERSION_GOVERNANCE.md)
- [InfluxDB Time-Series Platform Version Governance](../reference/INFLUXDB_VERSION_GOVERNANCE.md)
- [QuestDB Time-Series Database Version Governance](../reference/QUESTDB_VERSION_GOVERNANCE.md)
- [ISO/IEC 27040:2015 Storage Security Governance](ISO_IEC_27040_2015_STORAGE_SECURITY_GOVERNANCE.md)
- [NIST SP 800-189 Immutable Storage Governance](NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [Backup Coverage Review](../playbooks/BACKUP_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Retention policy** — the maximum age beyond which a time-series row is automatically deleted by the database.
- **Compression** — the on-disk encoding that reduces the storage footprint of time-series rows (native columnar compression, dictionary encoding, delta-of-delta, Gorilla-style encoding).
- **Tiered storage** — the migration of older chunks / partitions from a primary (hot) tier to a lower-cost (cold) tier.
- **Archival** — the export of older chunks / partitions to a long-term immutable object store; see [NIST SP 800-189 Immutable Storage Governance](NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
- **Compression ratio** — the ratio of uncompressed to compressed size, measured per chunk / partition.

## 4. Retention policy

1. Every time-series table declares a retention policy expressed in days (or seconds) in the manifest.
2. Retention policies are enforced by the database's native retention scheduler; ad-hoc deletes are prohibited.
3. Retention policy changes are declared in the manifest with an effective date; runtime override is prohibited without a change ticket.
4. Retention breaches (data older than the policy that is still on disk) produce an alert to the workload owner.

## 5. Compression

1. Every time-series table declares a compression policy (segment-by, order-by, compression_after) in the manifest.
2. Compression is enabled for chunks older than the declared threshold; pre-compression data is hot for ingestion, post-compression data is hot for query.
3. Compression algorithms are selected from the database's certified catalog; bespoke algorithms require a documented justification and a performance review.
4. Compression ratio is monitored per chunk / partition; ratios below the declared minimum trigger a remediation ticket.

## 6. Tiered storage

1. Older chunks / partitions are migrated to a lower-cost tier (object storage, cold-block storage) after the declared migration window.
2. Tier migration is transparent to queries; the database's query planner transparently fetches from the cold tier as needed.
3. Tier migration is irreversible by default; reverse migration (cold → hot) requires a change ticket and a capacity review.
4. Cold-tier cost is monitored at least every 90 days; cost anomalies trigger a remediation ticket.

## 7. Archival

1. Time-series data older than the retention policy is archived to a long-term immutable object store before deletion; see [NIST SP 800-189 Immutable Storage Governance](NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
2. Archival is performed via the database's native archival tool or a documented custom pipeline; the pipeline is recorded in the manifest.
3. Archived data is encrypted with a key scoped to the workload; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
4. Archival retention meets the duration mandated by the applicable regulation; the default is 7 years.

## 8. Deletion and right-to-erasure

1. Personal-data time-series values are deleted upon a right-to-erasure request; the deletion is propagated via the standard data-lifecycle pipeline.
2. Deletion events are recorded in the central audit pipeline; see [Backup Coverage Review](../playbooks/BACKUP_COVERAGE_REVIEW.md).
3. Deletion is performed at the database level; downstream caches and feature / vector stores must be invalidated as part of the deletion procedure.
4. Deletion is verified at the database level and at the downstream cache / feature / vector stores before the ticket is closed.

## 9. Capacity planning

1. Ingest rate, storage growth, and query rate are forecasted per workload at least every 90 days.
2. Forecasts are compared against provisioned capacity; deviations above the declared threshold trigger a capacity expansion ticket.
3. Cold-tier cost is forecast separately and compared against the workload's storage budget.
4. Capacity anomalies produce an alert to the workload owner and to the Time-Series Platform team.

## 10. Security

1. Time-series data at rest is encrypted using envelope encryption with keys stored in the central KMS; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
2. Snapshots and archives inherit the encryption posture of the source store.
3. Personal-data time-series values are encrypted with a tenant-scoped key; key rotation follows the KMS rotation policy.
4. Retention and compression changes affecting personal data require a documented security review.

## 11. Operating model

1. The Time-Series Platform team owns the shared retention and compression configuration.
2. Workload owners own their retention policies, compression policies, and capacity forecasts.
3. The Time-Series Platform guild meets monthly to review storage growth, cold-tier cost, and adoption of new compression algorithms.
4. New compression algorithms or tiered-storage backends are evaluated by the Time-Series Platform team and approved by the Storage team.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Storage team. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
