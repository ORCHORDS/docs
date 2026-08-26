# read-replicas-routing

**Issue:** All queries hit primary database, wasting read capacity of replicas
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Primary CPU saturated with SELECT queries. Read replicas idle. Application always connects to single primary endpoint.

## Pattern / Solution
Route read-only queries to replica pool, writes to primary. Use Postgres streaming replication for replicas. Monitor replica lag via pg_stat_replication.replay_lag and do not route reads that need fresh post-write data.

## Gotchas
- Replication lag means replicas may be behind; do not route reads that need fresh data post-write
- Long-running queries on replicas can block vacuum on primary (hot standby feedback)
- Read-your-writes pattern breaks with naive round-robin to replicas

## Related
- eventual-consistency-patterns
- cqrs-read-write-split
- connection-pooling-pgbouncer
