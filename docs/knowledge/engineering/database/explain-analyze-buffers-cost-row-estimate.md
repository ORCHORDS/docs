# Explain Analyze Buffers Cost Row Estimate

## Scope

This article covers how to read PostgreSQL `EXPLAIN ANALYZE` output with `BUFFERS` enabled to diagnose query performance, with specific attention to the relationships between estimated rows and actual rows, plan cost and real cost, buffer hits versus reads, and the operations that most often produce misleading plans. It is a calibration guide for the planner output, not a recipe for any one query shape, and applies to PostgreSQL 12 and newer (some output fields like `Heap Fetches` are version-dependent). It excludes alternatives such as `auto_explain`, third-party profilers, and the specific tuning of `pg_stat_statements` thresholds.

## Workflow or implementation guidance

1. **Always run with `ANALYZE, BUFFERS`.** `EXPLAIN` alone shows what the planner *expected*; `EXPLAIN (ANALYZE, BUFFERS)` shows what actually ran and what was paid in I/O. Plan-only output is fine for showing shape during development but cannot diagnose cost problems.
2. **Read from the bottom up.** The planner builds the tree bottom-up and produces the deepest nodes first. In a textual plan, the deepest `actual time` value is the first cost incurred; large time deltas between a parent node and its children point to where the work is happening.
3. **Compare estimated rows to actual rows.** A divergence of 10x or more between the planner's estimate and the actual count almost always signals a statistics problem. Run `ANALYZE` on the underlying table; if divergence persists, raise `default_statistics_target` for that column or use `ALTER ... SET STATISTICS`. Persistent divergence with current statistics is a hint that the planner's cost model is wrong for that distribution (highly skewed, correlated, or non-uniform columns).
4. **Distinguish `shared hit` from `shared read`.** Hits are buffer-cache reads; reads are disk reads and are roughly two orders of magnitude more expensive. A plan that is mostly hits but high in `actual time` is CPU-bound; a plan with many reads is I/O-bound and the right fix is an index, a covering index, or a cache, not a query rewrite.
5. **Look for loops and their counts.** Nested-loop joins multiply the inner cost by the number of outer rows. A `loops=1000` on an inner node whose `actual time=0.5` is not negligible — 500 ms is a 1000-iteration nested loop. The textual plan can hide this; the JSON plan makes it explicit and is preferable for serious diagnosis.
6. **Watch for `Sort Method: external merge Disk`.** When the working set exceeds `work_mem`, the sort spills to disk. Either raise `work_mem` for the session that runs the query or reduce the row count earlier in the plan so the sort fits.
7. **Use `FORMAT JSON` for diffing.** A textual plan is hard to compare across runs; the JSON form is stable enough to diff in CI or before/after tuning. Track the per-node `(actual rows, actual time, shared hit, shared read)` tuples across runs to see what actually moved.
8. **Read plan-cost as a relative ranking, not a prediction.** The cost numbers (`cost=0.00..18.50`) are planner-relative and unitless in any useful sense. Use them to compare two candidate plans for the same query, not to predict absolute wall time.
9. **Validate with cold-cache runs when I/O matters.** A plan that hits the buffer cache entirely will not reproduce the cost you see in production with a cold cache. Compare runs that flush caches between executions to expose the real disk cost.
10. **Cross-check with `pg_stat_statements`.** The plan explains one invocation; `pg_stat_statements` shows aggregate behaviour across many calls. A query whose plan looks fine but whose `pg_stat_statements` shows high mean time is a candidate for caching, deduplication, or rate limiting.

## Controls

1. **Standardized `EXPLAIN` invocation.** Every performance investigation uses `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` so output is comparable across engineers and tools.
2. **Plan diff in CI.** For benchmarked hot queries, a stored baseline JSON plan; PRs that change the plan in a meaningful way (different node type, cost increase over a threshold) are flagged for review.
3. **`pg_stat_statements` enabled and exported.** Top queries by `total_exec_time` are visible to anyone investigating latency.
4. **`auto_explain` for production traces.** Configured with `log_min_duration` at a sensible threshold so slow queries are captured without log spam; this prevents relying on reproduced workloads for diagnosis.
5. **Statistics refresh policy.** A periodic check on `pg_stat_all_tables.n_mod_since_analyze` so frequently-updated tables do not drift past the autovacuum threshold into stale-plan territory.
6. **Cost sanity test.** When introducing a new query or index, run with `ANALYZE` and assert `(estimated rows / actual rows)` is within a tolerable ratio (commonly 0.1–10x).

## Validation evidence

1. **Cold-cache comparison.** Repeat the query after `pg_buffercache` flushing and confirm that the `Buffers:` line now shows `read` rather than `hit`, validating the I/O-bound diagnosis.
2. **`ANALYZE` improves estimate.** Run `EXPLAIN ANALYZE` before and after `ANALYZE` on a recently-bulk-loaded table; assert the row-estimate divergence narrows and the chosen plan matches the best-known plan.
3. **`work_mem` test.** Run the same query with `work_mem = '4MB'` and `work_mem = '64MB'`; assert the sort spill disappears in the latter, and time the wall-clock difference.
4. **Index utilization test.** Add an index, re-run `EXPLAIN ANALYZE`, and confirm the chosen node changes from `Seq Scan` to `Index Scan` or `Index Only Scan`; if it does not, the index is not doing what its name suggests and should be reviewed.
5. **Aggregate correlation.** Compare the `EXPLAIN ANALYZE` cost to the `pg_stat_statements` `mean_exec_time` for the same query over a sample window; large divergences indicate the planner is being lied to or the workload is unusual.

## Failure modes and correction

1. **Stale statistics produce wrong plan.** Symptom: row-estimate divergence grows after a bulk load; the chosen plan degenerates. Correction: `ANALYZE` the affected table; consider increasing autovacuum frequency for write-heavy tables.
2. **`Seq Scan` chosen because the table is "small enough".** The planner legitimately picks a seq scan over an index scan when the table is small, the cache is hot, and the index would add random I/O. Correction: do not add an index that the planner correctly refuses to use; instead look at the upper bound on table size that would justify the index and re-evaluate then.
3. **Bloating causes the wrong index to be chosen.** Symptom: query latency rises after heavy updates/deletes; the index would be correct on a vacuumed table. Correction: aggressive autovacuum and periodic `VACUUM FULL` or `pg_repack`.
4. **`work_mem` spill hides the real bottleneck.** Symptom: a hash or sort node dominates the time, but the cost is unrelated to algorithm choice. Correction: raise `work_mem` for the session, then re-examine; permanent raise requires understanding the side effects on overall memory use.
5. **Plan-cache flip produces a bad plan.** Symptom: a query that worked fine yesterday is suddenly choosing a different plan after `pg_stat_statements` re-aggregation. Correction: investigate custom-vs-generic plan behaviour and pin `plan_cache_mode` if necessary.
6. **Buffer-cache noise misleads tuning.** Symptom: a benchmark in dev runs entirely from cache and looks great; production with cold cache shows the real cost. Correction: run benchmarks with controlled cache states, ideally a representative cold-cache scenario.

## Limitations

1. **`EXPLAIN ANALYZE` itself runs the query and consumes database time;** it is not free and is not safe to run uncritically against an already-slow production query.
2. **`cost` values are unitless;** they predict the *cheapest* plan, not the wall time. Two plans with similar cost can differ wildly in latency when the planner's cost model misjudges the dominant factor.
3. **Buffer cache state is volatile;** comparing two `EXPLAIN ANALYZE` runs across different cache states is misleading.
4. **Plans do not reveal optimizer bugs.** Some pathological plans persist across `ANALYZE` and tuning, indicating the cost model itself is wrong for that data distribution; correcting this requires schema or query changes that planner-side knobs cannot fix.
5. **Output fields evolve across PostgreSQL versions**; any tool that diffs plans across versions must be aware of schema changes to avoid false alarms.

## Canonical sources

- PostgreSQL Documentation, Using EXPLAIN: https://www.postgresql.org/docs/current/using-explain.html
- PostgreSQL Documentation, EXPLAIN reference (SQL syntax): https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL Documentation, Statistics Used by the Planner: https://www.postgresql.org/docs/current/planner-stats.html