# Time Range Index Btree Vs Brin Selection

## Scope

This article covers index selection for time-range queries on large PostgreSQL tables: when to choose a B-tree index on the timestamp column versus when to choose a Block Range Index (BRIN), and how each index performs on append-only or naturally-ordered data versus random-update patterns. It addresses the recurring decision in time-series workloads, where the table grows by millions of rows per day and the workload is dominated by "rows from the last N days" queries. It excludes partitioning (which solves a related problem) and dedicated time-series stores (TimescaleDB, InfluxDB); BRIN is a built-in tool that competes with both.

## Workflow or implementation guidance

1. **Use B-tree when the table is large *and* queries need a specific point lookup or a small range.** B-tree indexes are general-purpose; they support equality, range, and `ORDER BY` on the indexed column, and they are efficient even when the data is randomly ordered. The trade-off is size: a B-tree on a billion-row table is hundreds of gigabytes.
2. **Use BRIN when the table is large, naturally ordered by the indexed column, and queries cover wide ranges.** BRIN stores block-range summaries (minimum and maximum values per block range), so a query `WHERE created_at > $1 AND created_at < $2` can skip entire block ranges that lie entirely outside the range. The index size is roughly 0.1% of the table size, but the index is useless for point lookups and for data that is not naturally ordered.
3. **Make the data ordering match the index.** BRIN's summaries assume that rows in adjacent blocks have correlated values of the indexed column. If the table is loaded in random order or receives frequent updates that re-shuffle values within a block, the BRIN summaries become misleading and the index degrades to a near-seq-scan. The canonical BRIN workload is append-only time-series tables where new rows are appended in time order.
4. **Tune the BRIN `pages_per_range` parameter to match the workload.** The default of 128 pages per range is a starting point; larger values shrink it further but make range filtering coarser. The right value depends on how much data a query typically fetches relative to the block range.
5. **Combine BRIN with a small B-tree on a secondary key.** A common pattern is BRIN on `created_at` for wide-range queries and B-tree on `(created_at, sensor_id)` for the hot subset. The BRIN handles "give me the data for the last 24 hours"; the B-tree handles "give me the last reading from sensor X".
6. **Reconsider BRIN when updates are frequent.** An update that changes a row's `created_at` value may shuffle the row to a new block, invalidating the BRIN summary for both the old and the new block range. On a heavily updated table, BRIN degrades; either partition the table to limit updates to a small recent partition, or fall back to B-tree.
7. **Use the `AUTOSUMMARIZE` option for large initial loads.** `CREATE INDEX ... WITH (autosummarize = on)` populates BRIN summaries as new blocks are appended, avoiding a one-off `BRIN Summarize` after a bulk load. The cost is some CPU during writes.
8. **Compare B-tree and BRIN with realistic workloads before committing.** A staging comparison of `EXPLAIN ANALYZE` for the hot query shapes against a realistic dataset, with cache and replication state matching production, is the only way to confirm the trade-off.
9. **Mind `NULL` handling.** BRIN tracks minimum and maximum; `NULL` rows are summarised as if they were the minimum (or as defined by the operator class). Test how queries that filter on `IS NULL` or `IS NOT NULL` interact with the index.
10. **Avoid BRIN as a substitute for partitioning.** BRIN shrinks the index, not the table. A billion-row table with BRIN still has a billion rows; a query that fails to prune the BRIN scans the whole thing. Partitioning physically separates the data so a query that filters on the partition key avoids most of the rows entirely.

## Controls

1. **Index utilisation dashboard.** A periodic report on `pg_stat_user_indexes` showing scans and tuples fetched per index; a B-tree whose scans drop in favour of a BRIN is the expected pattern, but a BRIN whose scans fall to zero is a sign it is unused.
2. **BRIN summary health.** A check that BRIN summaries are up-to-date for the most recently appended blocks; `VACUUM` (which auto-summarises by default) keeps this current.
3. **Update-pattern monitor.** A periodic count of `UPDATE`s on the time column for tables with a BRIN; a spike indicates the index may be misleading the planner.
4. **Workload benchmark cadence.** A scheduled benchmark comparing B-tree and BRIN for the hot queries against a fixture; the trade-off can shift as the data distribution changes.
5. **Partition boundary review.** Tables with both BRIN and partitioning must define the boundaries so that BRIN works well within a partition; misalignment can compound.
6. **`pages_per_range` policy.** A documented default per table family; reviewed when the data shape changes (for example, when bulk loads switch from row-by-row to batched `COPY`).

## Validation evidence

1. **Range-scan test.** Compare `EXPLAIN ANALYZE` for a wide-range query (for example, "last 30 days") against the B-tree and BRIN indexes; assert the BRIN reports a much smaller index size and at least comparable execution time.
2. **Point-lookup test.** Compare the same for a point-lookup query (a row by exact `created_at`); assert the B-tree is selected and the BRIN is not (the planner correctly avoids BRIN for point lookups).
3. **Bulk-load and auto-summarise test.** Run a bulk load against a BRIN with `autosummarize = on`; assert the summaries appear for newly appended blocks without manual `VACUUM`.
4. **Update-degradation test.** Run a workload that updates the indexed column on a fraction of rows; assert that BRIN's effectiveness degrades (queries may start scanning more pages) and document the threshold at which B-tree becomes the right choice.
5. **Cost comparison against partitioning.** Compare BRIN's cost savings to partitioning's cost savings for the same workload; the smaller of the two is the right architectural choice unless the team has a reason to combine them.

## Failure modes and correction

1. **BRIN returns stale summaries for a recent block range.** Symptom: a query that should hit a recently appended block range does not use the index. Correction: run `VACUUM` to trigger summarisation, or enable `autosummarize`.
2. **Data inserted out-of-order undermines BRIN.** Symptom: queries that should use the index start scanning more pages than expected; the summary is misleading. Correction: insert rows in time order (backfill in time order if necessary), or fall back to B-tree.
3. **`pages_per_range` is too large for the workload's selectivity.** Symptom: BRIN is selected but pages per range are coarse, leading to unnecessary heap fetches. Correction: lower `pages_per_range` to a value that matches the typical query range width.
4. **`pages_per_range` is too small and the index is large.** Symptom: BRIN consumes more space than expected; build/maintenance cost is high. Correction: raise `pages_per_range` to a value that still prunes effectively.
5. **B-tree keeps growing without bound on a time-series table.** Symptom: index size dwarfs table size; insert throughput degrades. Correction: switch to BRIN or partitioning; verify with the workload benchmark.
6. **BRIN chosen for a table that is heavily updated.** Symptom: query plans degrade over time as the data becomes less ordered. Correction: replace BRIN with B-tree, or partition so updates land in a small recent partition while the BRIN covers the historical ones.

## Limitations

1. **BRIN does not support point lookups or `ORDER BY` for index-only access**; a B-tree is required for those query shapes.
2. **BRIN depends on data ordering;** if rows are not naturally ordered by the indexed column, the index is wasted.
3. **BRIN does not shrink the table;** it shrinks only the index. A 1 TB table with a 1 GB BRIN still takes 1 TB to scan if the planner fails to prune.
4. **BRIN summaries are coarse;** queries that overlap block boundaries may still visit many pages that did not contain matching rows.
5. **Combining BRIN with `INCLUDE` columns is supported but rarely useful;** BRIN is not a covering-index candidate in the same way B-tree is.

## Canonical sources

- PostgreSQL Documentation, BRIN Indexes: https://www.postgresql.org/docs/current/brin.html
- PostgreSQL Documentation, Index Types (overview): https://www.postgresql.org/docs/current/indexes-types.html
- PostgreSQL Documentation, Built-in BRIN Operator Classes: https://www.postgresql.org/docs/current/brin-builtin-opclasses.html