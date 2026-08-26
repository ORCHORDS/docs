# postgres-monitoring-queries

**Issue:** No visibility into Postgres internals without knowing the right system catalog queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Slow queries, bloat, lock contention, replication lag -- all diagnosable from system views if you know where to look.

## Pattern / Solution
Key queries: pg_stat_activity WHERE state = 'active' ORDER BY duration DESC for long-running queries. pg_locks JOIN pg_stat_activity WHERE NOT granted for lock waits. pg_stat_user_tables for bloat. pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20 for top queries.

## Gotchas
- pg_stat_statements requires the extension to be created and shared_preload_libraries to include it
- pg_stat_activity may show internal autovacuum workers -- filter with application_name
- Replication lag: SELECT now() - pg_last_xact_replay_timestamp() on replica

## Related
- explain-analyze-reading
- vacuum-and-bloat-postgres
- postgres-configuration-tuning
