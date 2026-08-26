# PostgreSQL Plan Cache Mode and Parameter-Skew Diagnosis

**Issue:** Prepared statements can regress after PostgreSQL switches from parameter-aware custom plans to a reusable generic plan, especially when tenant size or value frequency is highly skewed.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Why it matters

PostgreSQL normally uses custom plans for the first five executions of a parameterized prepared statement, compares their average estimated cost with a generic plan, and may then reuse the generic plan. Reuse saves planning time, but a plan that is acceptable for a common parameter can be disastrous for an outlier. Poolers, ORMs, and long-lived application processes make this transition easy to miss.

## Control pattern

1. Preserve the default `plan_cache_mode=auto` globally.
2. Identify a stable statement identity and compare representative high- and low-cardinality parameters with `EXPLAIN (ANALYZE, BUFFERS)`.
3. Use `EXPLAIN (GENERIC_PLAN)` where supported to inspect the parameter-independent plan without executing the query.
4. Compare `pg_stat_statements` execution-time dispersion and plan counts before attributing latency to the cache.
5. Apply `SET LOCAL plan_cache_mode = force_custom_plan` only inside the affected transaction or narrow application path after evidence shows the generic plan is harmful.
6. Prefer fixing stale statistics, missing indexes, or query shape before making a persistent override.

## Verification

- Reproduce the sixth and later executions in a staging dataset with realistic skew.
- Record planning time, execution time, row-estimate error, buffer reads, and chosen scan/join types.
- Confirm the override improves tail latency enough to offset repeated planning.
- Load-test through the actual driver and pooler because server-side and client-side preparation policies differ.
- Recheck after major data-distribution or PostgreSQL-version changes.

## Gotchas

`plan_cache_mode` is considered when a cached plan is executed, not when it is prepared. Forcing custom plans everywhere increases CPU and latency for statements where reuse is beneficial. A single fast parameter is not proof; test a distribution and retain the full correctness suite.

## Sources

- [PostgreSQL PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html)
- [PostgreSQL query-planning configuration](https://www.postgresql.org/docs/current/runtime-config-query.html)
- [PostgreSQL pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html)
