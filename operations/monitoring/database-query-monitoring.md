# database-query-monitoring

**Issue:** Monitoring database query performance and catching slow or expensive queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Application is slow but application metrics look fine. The bottleneck is in the database layer.

## Pattern / Solution
Enable pg_stat_statements (PostgreSQL) or performance_schema (MySQL). Export slow query metrics to Prometheus via postgres_exporter or mysqld_exporter. Alert on rows where mean_exec_time is greater than 100ms. Use Datadog Database Monitoring or New Relic for query-level APM without manual exporter setup. Track query count, rows scanned, and lock wait time per query fingerprint.

## Gotchas
pg_stat_statements requires shared_preload_libraries configuration — needs restart. Reset stats periodically to avoid stale aggregates. Monitor lock contention separately via pg_locks. Index miss rate (seq_scan ratio) is a leading indicator of query regressions.

## Related
slow-query-logging, connection-pool-monitoring, apm-transaction-tracing
