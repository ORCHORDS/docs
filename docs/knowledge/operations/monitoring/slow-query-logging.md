# slow-query-logging

**Issue:** Capturing and analyzing slow database queries for optimization
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
High database CPU or latency with no clear cause. Need to identify which queries are most expensive.

## Pattern / Solution
PostgreSQL: set log_min_duration_statement to 200ms to log queries over threshold. Parse logs with pgBadger to generate slow query reports. MySQL: enable slow_query_log with long_query_time 0.2. Export slow query log to Elasticsearch. For continuous monitoring use pg_stat_statements rather than log parsing — lower overhead, always on. Review top 10 slowest queries weekly.

## Gotchas
Log-based slow query analysis has latency. In high-traffic environments slow query logs can be voluminous — use log sampling. auto_explain PostgreSQL extension captures execution plans for slow queries. Never run EXPLAIN ANALYZE on production during an incident — it executes the query.

## Related
database-query-monitoring, connection-pool-monitoring, log-sampling-strategies
