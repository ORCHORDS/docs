# Prepared Statement Plan Cache Pollution

## Scope

This article covers plan-cache behaviour for PostgreSQL prepared statements: how the planner switches between custom plans (built for specific parameter values) and generic plans (built once and reused), the consequences for performance under skewed data distributions, and the strategies for configuring `plan_cache_mode` and managing pollution from many distinct query shapes. It addresses the specific concern that a single highly-parameterised statement, once it switches to a generic plan, can drag performance for all parameter values — a phenomenon often referred to as "plan cache pollution". It excludes server-side stored procedure compilation (PL/pgSQL), application-side caching of query results, and Postgres extensions that override planning entirely.

## Workflow or implementation guidance

1. **Understand the default switch.** PostgreSQL generates a custom plan for the first five executions of a prepared statement; the sixth uses a generic plan. This is the default behaviour governed by the cost-based decision the planner makes when it has accumulated enough statistics on the statement.
2. **Pin `plan_cache_mode = force_custom_plan` for hot statements with skewed data.** A workload like "lookup user by id" with a hot-id-skewed distribution will use a different plan depending on whether the id points to a popular or rare user. A generic plan uses the average distribution; a custom plan uses the supplied parameter. Hot reads should usually be `force_custom_plan`.
3. **Use `force_generic_plan` for stable, low-variance statements.** A statement that filters on a single high-cardinality key with uniform distribution performs similarly across parameter values; the generic plan saves repeated planning cost and is the right choice.
4. **Use the default `auto` for statements whose parameter selectivity is unknown.** The planner's switch decision is correct in the majority of cases; only override when you have evidence that a switch has hurt performance.
5. **Configure per-session or per-statement.** `SET plan_cache_mode = force_custom_plan` applies to the session; for individual statements, the application can issue `SET LOCAL` immediately before preparing the statement. A common pattern is to set it for the connection pool that serves the hot read paths and leave it default elsewhere.
6. **Manage statement count.** Each distinct SQL string creates a separate prepared statement entry; thousands of distinct strings (often caused by an ORM that emits SQL with many optional clauses) inflate the cache and dilute statistics. Adopt `WHERE a = $1 AND b = $2` parameterised forms, not `WHERE a = 1 AND b = 2` literal concatenation, so equivalent queries share a plan slot.
7. **Avoid statement churn on hot paths.** Invalidate-on-update caches (Postgres' own plan cache invalidates on `ANALYZE` or schema change for the affected relation) are correct, but application-level caches that re-prepare every request waste planning time. Re-use prepared statement handles; only re-prepare on error.
8. **Detect pollution before it becomes a regression.** Poll `pg_stat_statements` for queries whose plan has changed; a query that previously ran fast with `force_custom_plan` may now be running with a generic plan and regressing. Combine with application-level metrics on per-query latency.
9. **Test with representative parameter sets.** A plan that performs well in development may perform poorly in production because the production traffic includes parameter values the development test never exercised. Run the workload with a sampled distribution.
10. **Cooperate with the pooler.** Transaction-mode poolers may assign different server connections to the same client connection across executions; each server sees the planning history. Plan-cache behaviour is per-server-connection, not per-client; the consequences are visible to anyone debugging.

## Controls

1. **`plan_cache_mode` per connection pool.** Each connection pool serving a different query shape is documented with its `plan_cache_mode` setting; review on every change to the workload.
2. **Plan-flip detection.** A scheduled check that compares the most recent `EXPLAIN (GENERIC_PLAN)` against the most recent `EXPLAIN (ANALYZE)`; large divergence is a flag for `force_custom_plan`.
3. **Statement count budget.** A metric on the number of distinct prepared statements per server connection, with an alert when it crosses a threshold; high cardinality suggests an ORM that is not parameterising.
4. **Per-query latency regression test.** CI test that asserts latency for representative parameter values; fails when a generic plan degrades any of them beyond the threshold.
5. **Pooler interaction note.** A documented expectation that plan-cache behaviour is per-server-connection; debuggers check `pg_stat_activity` for the actual session, not the application connection.
6. **Statement timeout for planning.** `statement_timeout` is bounded so a runaway plan cannot hold a transaction indefinitely; planning time is small relative to execution, but locks held during planning are still meaningful.

## Validation evidence

1. **Custom vs generic plan test.** Prepare a query with a skewed distribution; execute it with the popular parameter and an uncommon parameter; compare latencies under `auto`, `force_custom_plan`, and `force_generic_plan`; assert the right mode for the workload is selected.
2. **Statement-count test.** Confirm that running the application for a representative period keeps the number of distinct prepared statements bounded; a runaway indicates an ORM bug or a missing parameterisation.
3. **Plan-flip test.** Force a flip by manipulating `default_statistics_target` or by issuing `ANALYZE`; assert the application behaviour is bounded (latency regression is capped, and the application falls back gracefully).
4. **`EXPLAIN (GENERIC_PLAN)` review.** Capture the generic plan for each hot statement during CI and review it; a generic plan that does not use the indexes used by the custom plan is a regression.
5. **Pooler-rotation test.** Run the same workload against a transaction-mode pooler with many client connections; assert the prepared-statement plan-cache behaviour is consistent across server connections.

## Failure modes and correction

1. **Generic plan uses a different index than the custom plan.** Symptom: query latency jumps after the planner switch. Correction: set `plan_cache_mode = force_custom_plan` for that statement's session, or rewrite the query to be less sensitive to parameter selectivity.
2. **ORM emits many distinct prepared statements.** Symptom: `pg_prepared_statements` count grows; cache is diluted; each statement lacks enough statistics to plan well. Correction: parameterise the query, eliminate conditional clauses that change the SQL text, or use a query builder that produces a stable shape.
3. **Plan invalidation storm after a bulk `ANALYZE`.** Symptom: a single `ANALYZE` invalidates many plans; the next batch of requests pays the planning cost. Correction: schedule `ANALYZE` for known table changes, or raise `default_statistics_target` to reduce sensitivity.
4. **Hot read paths slowed by a generic plan.** Symptom: latency p99 for a hot read query doubles after the sixth execution. Correction: switch to `force_custom_plan` for the affected pool or session; confirm the application-level metrics recover.
5. **Plan cache grows beyond memory budget.** Symptom: backend memory grows over time. Correction: cap the prepared-statement count at the application level; release handles on error.
6. **Server-side prepared statement invalidated by server restart.** Symptom: first request after a failover errors with "prepared statement does not exist". Correction: catch the error, re-prepare, and retry; ensure connection-pool warmup logic re-establishes statements.

## Limitations

1. **Postgres does not expose plan-cache contents in detail**; diagnosing plan cache behaviour requires `EXPLAIN` and `pg_stat_statements` rather than a direct cache view.
2. **Plan cache is per server connection**, not per database; coordination across a pool requires application-level policy.
3. **`force_generic_plan` does not improve performance for all statements**; some statements genuinely benefit from custom planning and regress under generic.
4. **Custom plans have their own cost.** The planner runs per execution, and very hot statements can spend measurable time in planning; for those, `force_generic_plan` may actually win.
5. **The default of five custom plans is a heuristic;** it is wrong for some workloads, and there is no knob to set "do exactly N custom plans before switching".

## Canonical sources

- PostgreSQL Documentation, PREPARE: https://www.postgresql.org/docs/current/sql-prepare.html
- PostgreSQL Documentation, Plan Caching (under PREPARE): https://www.postgresql.org/docs/current/sql-prepare.html#SQL-PREPARE-PLAN-CACHING
- PostgreSQL Documentation, pg_stat_statements (aggregate plan-cache view): https://www.postgresql.org/docs/current/pgstatstatements.html