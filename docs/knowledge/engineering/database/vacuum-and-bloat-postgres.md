# vacuum-and-bloat-postgres

**Issue:** Dead tuples accumulate in Postgres tables, causing table bloat and slowing queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Table size grows even after many deletes. pg_relation_size much larger than expected. Query plans show sequential scans reading far more pages than live rows justify.

## Pattern / Solution
VACUUM reclaims dead tuple space for reuse within the same table. VACUUM FULL rewrites the table and returns space to OS but requires exclusive lock. Monitor with pg_stat_user_tables.n_dead_tup. For severe bloat without downtime, use pg_repack extension.

## Gotchas
- Long-running transactions prevent VACUUM from removing dead tuples
- VACUUM FULL blocks all reads and writes -- never run on production without maintenance window
- Temporary tables do not autovacuum -- drop them explicitly after use

## Related
- autovacuum-tuning
- table-partitioning-postgres
- postgres-configuration-tuning
