# autovacuum-tuning

**Issue:** Default autovacuum settings are too conservative for high-write tables
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Autovacuum not keeping up. Table bloat growing. Dead tuple count consistently high in pg_stat_user_tables.

## Pattern / Solution
Tune per-table: ALTER TABLE hot_table SET (autovacuum_vacuum_scale_factor = 0.01, autovacuum_vacuum_threshold = 100, autovacuum_vacuum_cost_delay = 2). For very large tables, scale factor of 0.2 (default) means 20% dead before vacuum -- use 0.01 or 0.02.

## Gotchas
- autovacuum_vacuum_cost_delay default throttles I/O; set lower for busy tables
- Tables with many updates also need frequent autoanalyze for fresh statistics
- RDS and managed Postgres may restrict some GUC changes

## Related
- vacuum-and-bloat-postgres
- statistics-update-analyze
- postgres-configuration-tuning
