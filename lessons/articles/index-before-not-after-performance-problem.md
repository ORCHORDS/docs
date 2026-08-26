# index-before-not-after-performance-problem

**Issue:** Adding indexes to a large production table under load causes prolonged locks and worsens the outage
**Date:** 2026-08-11
**Status:** documented

## What happened
A team noticed slow queries on a 200M-row table. They added a missing index in production during business hours using a standard `CREATE INDEX`. The operation locked the table for 47 minutes. Orders could not be written. The fix caused more downtime than the slow queries.

## The lesson
Add indexes before the table grows large enough to make the operation painful. When you must add an index to a large table in production, use `CREATE INDEX CONCURRENTLY` (Postgres) or the equivalent non-blocking form for your database. Always test the operation on a production-sized dataset in staging first and time it.

## Why it matters
A missing index on a small table is a slow query. A missing index on a 200M-row table under peak load is an outage. Adding the index reactively compounds the problem. Proactive indexing during schema design costs nothing.

## How to apply
- [ ] During schema design, identify every column that will be used in a WHERE, JOIN, or ORDER BY clause and index it.
- [ ] Review EXPLAIN ANALYZE output in code review for any query touching more than ~10k rows.
- [ ] When adding an index to a live table, use non-locking index creation (`CONCURRENTLY` in Postgres).
- [ ] Test the index creation on a production-sized copy and measure the time before running in prod.
- [ ] Schedule large index operations during off-peak hours with monitoring active.

## Related
- `n-plus-one-queries-compound-at-scale.md`
- `monitor-before-and-after-deploy.md`
