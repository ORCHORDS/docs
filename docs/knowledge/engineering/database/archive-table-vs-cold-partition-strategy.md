# Archive Table Vs Cold Partition Strategy

## Scope

This article compares two strategies for keeping an operational table small while retaining historical rows for compliance or occasional audit: moving rows into a separate archive table (ETL-style copy-and-delete) versus declaring the same table as range-partitioned and letting cold data live in rarely-attached child partitions. It covers decision criteria, implementation steps, retention enforcement, and the operational consequences of each choice. It does not cover online archive systems like S3 + Athena, columnar warehouses, or the D1-specific hot/cold variants documented elsewhere in this leaf.

## Workflow or implementation guidance

1. **Decide by access pattern, not by fashion.** If archived rows are queried by a *different* application or only during investigations, a separate archive table with its own indexing is appropriate because it is invisible to the OLTP planner. If archived rows must appear in the same queries when a wide date filter is supplied (a five-year export, a year-over-year report), native partitions win because the parent table is a single logical object and no copy step exists.
2. **For the archive-table strategy, copy in batches inside a transaction per batch.** `INSERT INTO archive ... SELECT ... WHERE id IN (...)` followed by `DELETE ... WHERE id IN (...)`, with the batch size chosen so the delete holds row locks for well under a second. Wrap copy and delete in one transaction so a crash between them cannot lose rows; idempotency comes from a unique constraint on the archive's primary key plus `ON CONFLICT DO NOTHING`.
3. **Drive the move with a monotonic cursor, not a timestamp comparison alone.** Select rows by primary key ranges up to a cutoff, since `created_at` comparisons on an indexed-but-actively-updated column produce variable scan costs. Record the high-water mark in a small `archive_progress` table so restarts are deterministic.
4. **Verify then delete, then verify the delete.** After each batch, compare `count(*)` for the id-range in both tables inside one transaction before committing the delete. This is the only reliable protection against a partially-applied batch after a statement error.
5. **For the partition strategy, make the partition key part of every archival decision.** Declare the parent `PARTITION BY RANGE (created_at)`, create partitions ahead of need, and make retention a `DETACH PARTITION` plus `DROP TABLE` — a metadata operation that does not touch row data and does not bloat the parent.
6. **Pre-create partitions on a schedule and alert on the horizon.** A cron that creates the next month's (or day's) partition, plus an alert when the newest partition boundary is under 24 hours away, prevents the classic "no partition for this row" insert failure.
7. **Index the archive differently from the live table.** Archive access is almost always by entity id or a date window, not by the live table's hot selective predicates. Fewer, wider indexes on the archive reduce storage and write cost during the move.
8. **Do not mix both strategies on one table.** A partitioned table whose cold partitions are additionally copied to an archive table creates two sources of truth for the same rows and makes retention disputes unresolvable.

## Controls

1. **Retention policy encoded as configuration.** Retention days per table in a versioned config; the archival job reads it rather than hardcoding durations, so legal-hold exceptions are explicit changes.
2. **Legal-hold guard.** Before any `DETACH`/`DROP` or archive purge, the job checks a hold table keyed by entity id or date range and refuses to delete held rows.
3. **Batch size and lock budget.** A configurable batch size (typically 500-5000 rows) with a per-batch `lock_timeout`, plus a cap on batches per run so the job yields before autovacuum falls behind.
4. **Count reconciliation report.** A scheduled job asserting `live_count + archive_count = total_expected` per table, alerting on drift that would indicate a lost or duplicated batch.
5. **Horizon alert for partitions.** Monitoring on `pg_inherits`/catalog age of the newest partition, firing when the next partition is missing or imminent.
6. **Access control separation.** The archive table is owned by a role without application write access, making accidental writes from OLTP code path impossible.

## Validation evidence

1. **Batch integrity test.** Run the archival job against a staging table with 100k rows, kill it mid-run, restart, and assert the final counts match exactly with zero duplicates (unique constraint on archive PK) and zero missing ids.
2. **Concurrency test.** Run the archival batch while an application workload updates rows in the id range; assert no deadlock exceeds the lock budget and that no row is both updated in the live table and present in the archive.
3. **Partition detach timing.** Measure `DETACH PARTITION` on a multi-million-row child: it should complete in milliseconds regardless of row count, evidencing the metadata-only claim. Contrast with timing the equivalent row delete.
4. **Pruning proof.** Run `EXPLAIN` on a date-filtered query against the partitioned parent and confirm only partitions intersecting the filter appear in the plan, demonstrating that cold partitions cost nothing at plan time.
5. **Restore drill.** Quarterly, restore one archived batch (or one detached partition) into a scratch database and confirm application queries against it succeed — archival that has never been restored is unverified archival.

## Failure modes and correction

1. **Copy succeeds, delete fails, job retries and duplicates.** Without a unique constraint on the archive, retries duplicate rows. Correction: unique constraint plus `ON CONFLICT DO NOTHING`, making the whole move idempotent.
2. **Long-running delete blocks OLTP writes.** Symptoms are lock waits and replication lag spikes during archival windows. Correction: reduce batch size, move by primary-key ranges, run outside peak traffic, and set `lock_timeout` so the batch yields instead of queuing.
3. **Autovacuum falls behind the churn.** Massive row moves create dead tuples faster than default settings reclaim them, degrading scans. Correction: per-table autovacuum scaling factors for tables under archival churn, and a manual `VACUUM ANALYZE` after large runs.
4. **Missing partition causes insert failures.** An insert arriving for a range with no partition errors out. Correction: pre-creation cron plus horizon alerting; optionally a default partition to catch stragglers, monitored so silent accumulation is visible.
5. **Archive table drift from schema changes.** An `ALTER TABLE` on the live table is not applied to the archive, and the copy starts failing. Correction: archive table DDL is generated from the same migration as the live table, and a schema-comparison check runs before each archival job.
6. **Query planner statistics go stale after large moves.** Row estimates degrade after bulk deletes. Correction: `ANALYZE` both tables at the end of each archival run.

## Limitations

1. **The archive-table strategy cannot serve queries that span live and historical rows in one statement** without a view or union, which then re-implements partitioning poorly.
2. **Unique constraints on partitioned tables must include the partition key**, so a global uniqueness guarantee on an id alone is not enforceable natively.
3. **Partitioning adds operational surface**: creation jobs, horizon alerts, and per-partition index maintenance that a single table does not have.
4. **Neither strategy addresses storage cost by itself**; detached partitions still occupy the same cluster until dropped or exported.
5. **Cross-table foreign keys into an archived-away row** break referential integrity checks, so references must be relaxed or archived last.

## Canonical sources

- PostgreSQL Documentation, Table Partitioning: https://www.postgresql.org/docs/current/ddl-partitioning.html
- PostgreSQL Documentation, Routine Vacuuming: https://www.postgresql.org/docs/current/maintenance.html
- PostgreSQL Documentation, VACUUM: https://www.postgresql.org/docs/current/sql-vacuum.html
