# prepared-statements

**Issue:** Repeated queries re-parsed on every execution
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
High CPU from query planning overhead when the same query shape runs thousands of times per second. Visible in pg_stat_statements as high total_plan_time relative to total_exec_time.

## Pattern / Solution
Use named prepared statements server-side (PREPARE/EXECUTE in Postgres) or let your driver/ORM handle it via protocol-level prepared statement caching. In Node.js with pg, pass a name field to enable caching. In Postgres: PREPARE get_user (int) AS SELECT * FROM users WHERE id = ; EXECUTE get_user(42);

## Gotchas
- Prepared statements are session-scoped; connection poolers in transaction mode invalidate them
- PgBouncer in transaction pooling mode requires server_reset_query = DISCARD ALL or use of unnamed statements
- Generic plans vs custom plans: Postgres may use a generic plan after 5 executions, which can be worse for skewed data
- Use DEALLOCATE or connection close to free them

## Related
- parameterized-queries
- connection-pooling-pgbouncer
- query-plan-optimization
