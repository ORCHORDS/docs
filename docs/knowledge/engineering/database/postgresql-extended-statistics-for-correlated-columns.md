# PostgreSQL extended statistics for correlated columns

**Issue:** PostgreSQL can misestimate row counts when predicates involve correlated columns because ordinary per-column statistics assume independence.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use `CREATE STATISTICS` for demonstrated multi-column estimation problems. PostgreSQL supports statistics kinds including functional dependencies, multivariate distinct counts, and most-common-value combinations. Run `ANALYZE` after creating or changing the statistics so the planner has populated data.

Choose columns and expression sets from actual misestimated queries. Extended statistics add analysis and catalog cost and do not guarantee a particular plan.

## Operational controls

- Capture `EXPLAIN (ANALYZE, BUFFERS)` evidence before and after in a safe environment.
- Prefer the narrowest statistic set that addresses a recurring workload.
- Re-analyze after meaningful distribution changes.
- Track statistics definitions with schema migrations.
- Avoid using production `ANALYZE` options without evaluating I/O impact.
- Reassess after PostgreSQL upgrades or query-shape changes.

## Verification

1. Record estimated and actual rows for the target predicates.
2. Create the appropriate statistics object and run `ANALYZE`.
3. Compare estimates, plan, execution time, buffers, and planning time.
4. Test representative parameter values, including skewed cases.
5. Drop the statistics in a test environment and confirm the observed effect is attributable.

## Sources

- [PostgreSQL 18: Multivariate statistics examples](https://www.postgresql.org/docs/current/multivariate-statistics-examples.html)
- [PostgreSQL 18: CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html)
- [PostgreSQL 18: Planner statistics](https://www.postgresql.org/docs/current/planner-stats.html)
