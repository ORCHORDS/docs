# PostgreSQL Query Optimization — EXPLAIN ANALYZE, Index Types, and Query Plans

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your API endpoint takes 3 seconds to respond. The PostgreSQL query
behind it runs a sequential scan on a 10-million-row table despite
a WHERE clause on an indexed column — because the column comparison
involves an implicit type cast that disables index usage. Your ORM
auto-prepares statements, and a generic plan is cached that performs
worse than the custom plan for your skewed data distribution. You
have no visibility into which queries consume the most database time
because `pg_stat_statements` is not enabled.

## Context

PostgreSQL query optimization starts with reading EXPLAIN ANALYZE
output to understand how the planner executes queries. The planner
chooses between scan types (Seq Scan, Index Scan, Bitmap Heap Scan)
and join strategies (Nested Loop, Hash Join, Merge Join) based on
table statistics, index availability, and cost estimates. Index
selection (B-tree, GIN, GiST, BRIN) depends on the query pattern
and data distribution. `pg_stat_statements` identifies the worst
queries by total execution time, and `auto_explain` logs actual
query plans in production without manual reproduction.

## Reading EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) SELECT ...;
```

```
Key things to look for:

  1. Estimated vs actual rows
     → Large divergence = bad statistics (run ANALYZE)

  2. Time spent per node
     → Largest actual time delta between node and children
        is where time is spent

  3. Buffer hits vs reads
     → reads = disk I/O, hits = shared buffer cache

Scan node types:
  Seq Scan           Full table scan (fine on small tables)
  Index Scan         B-tree lookup + heap fetch per row
  Index Only Scan    B-tree only, no heap fetch (needs VACUUM)
  Bitmap Heap Scan   Build bitmap of pages, then sequential fetch
                     (good for medium selectivity or OR conditions)

Join node types:
  Nested Loop        Best for small outer set + indexed inner
  Hash Join          Builds hash table from smaller relation
  Merge Join         Requires sorted inputs (index or explicit sort)
```

## Index types

```
Type    Best for                     Notes
──────────────────────────────────────────────────────────────
B-tree  Equality, range, ORDER BY    Default; most common
GIN     Arrays, JSONB, full-text     Multi-value columns;
        tsvector                     PG18 added parallel builds
GiST    Geometric, ranges,          Nearest-neighbor queries
        nearest-neighbor (<->)       and exclusion constraints
BRIN    Large, naturally-ordered     Tiny index size; block-range
        tables (time-series)         summaries for append-only data
Hash    Equality-only               Rarely preferred over B-tree
```

## Advanced index techniques

```sql
-- Partial index: only index rows matching a condition
CREATE INDEX idx_pending_orders
  ON orders (created_at)
  WHERE status = 'pending';

-- Covering index (INCLUDE): enables index-only scans
CREATE INDEX idx_users_email
  ON users (email)
  INCLUDE (name, created_at);

-- Expression index: for function-based lookups
CREATE INDEX idx_users_lower_email
  ON users (lower(email));

-- PostgreSQL 18: skip scan on multicolumn B-tree
-- Efficient even when leading columns aren't filtered
-- Reduces need for redundant single-column indexes
```

## Common performance killers

```
Problem                          Fix
──────────────────────────────────────────────────────────────
Missing index on FK/join/filter  CREATE INDEX on the column
columns

Implicit type cast               Ensure column and parameter
WHERE id = '123' (text vs int)   types match exactly

Function on indexed column       Create expression index
WHERE lower(email) = ...         CREATE INDEX ON t (lower(email))

OR across different columns      Rewrite as UNION ALL, or
WHERE a = 1 OR b = 2             accept Bitmap Or scan

Unindexed foreign keys           CREATE INDEX on FK columns
                                 (slow cascading deletes)

Outdated statistics              Run ANALYZE on the table
(bad row estimates)              or enable autovacuum

Bloated tables                   VACUUM FULL or pg_repack
(dead tuple overhead)
```

## Diagnostic tools

```sql
-- pg_stat_statements: find worst queries by total time
-- Enable: shared_preload_libraries = 'pg_stat_statements'
SELECT query,
       calls,
       total_exec_time / 1000 AS total_seconds,
       mean_exec_time AS mean_ms,
       rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

```
auto_explain: log actual plans for slow queries

  shared_preload_libraries = 'pg_stat_statements,auto_explain'
  auto_explain.log_min_duration = '100ms'
  auto_explain.log_analyze = on
  auto_explain.log_buffers = on
  auto_explain.log_timing = on

  Logs actual EXPLAIN ANALYZE for queries exceeding threshold.
  Critical for catching slow plans in production without
  manual reproduction.
```

## Plan caching and prepared statements

```
PostgreSQL generates a generic plan after ~5 executions
of a prepared statement.

  Generic plan: one plan reused for all parameter values
  Custom plan: optimized for specific parameter values

  plan_cache_mode options:
    auto           — default, switches after 5 executions
    force_custom   — always generate custom plans
    force_generic  — always use generic plan

  Problem: generic plans can perform worse for skewed data
  distributions (e.g., status column where 99% are 'active').

  Common in ORMs that auto-prepare statements.
  Fix: SET plan_cache_mode = 'force_custom_plan' per session,
  or restructure the query to avoid the problematic case.
```

## Anti-patterns

- **Adding indexes without checking EXPLAIN** — indexes have
  write overhead. Verify the planner actually uses the index
  before adding it to production.
- **Using SELECT * in queries** — prevents index-only scans and
  fetches unnecessary columns. Select only needed columns.
- **Ignoring pg_stat_statements** — flying blind on which queries
  consume the most time. Enable it in every PostgreSQL deployment.
- **Running EXPLAIN without ANALYZE** — EXPLAIN alone shows
  estimates, not actual execution. Always use ANALYZE (with
  BUFFERS) to see real performance.

## Gotchas

- **Index-only scans need VACUUM** — the visibility map must be
  up to date for index-only scans to work. Tables with heavy
  writes need aggressive autovacuum settings.
- **ANALYZE vs VACUUM ANALYZE** — `ANALYZE` updates statistics
  only. `VACUUM ANALYZE` reclaims dead tuples AND updates
  statistics. Both are needed but serve different purposes.
- **GIN indexes and write performance** — GIN indexes are
  expensive to maintain on write-heavy columns. Use `fastupdate`
  (default on) to batch index updates, but be aware of delayed
  visibility.
- **Prepared statement plan flip** — after PostgreSQL switches to
  a generic plan, performance can silently degrade. Monitor
  `pg_stat_statements` after ORM upgrades that change prepared
  statement behavior.

## Verification

- `pg_stat_statements` enabled and monitored for top queries.
- `auto_explain` configured for queries exceeding threshold.
- EXPLAIN ANALYZE run for all critical query paths.
- Indexes created with verified planner usage.
- Partial and covering indexes used where appropriate.
- Autovacuum configured for write-heavy tables.
- Plan cache mode evaluated for skewed distributions.

## Related

- `documentation/categories/database/postgresql-connection-pool-tuning.md`
- `documentation/categories/database/zero-downtime-database-migrations.md`
- `documentation/categories/database/postgresql-jsonb-indexing-querying.md`

## Source URLs (verified 2026-08-16)

- PostgreSQL EXPLAIN Documentation — https://www.postgresql.org/docs/current/using-explain.html
- PostgreSQL Index Types — https://www.postgresql.org/docs/current/indexes-types.html
- pganalyze — Enable auto_explain — https://pganalyze.com/docs/explain/setup/self_managed/02_enable_auto_explain
- PostgreSQL 18 Released — https://www.postgresql.org/about/news/postgresql-18-released-3142/
