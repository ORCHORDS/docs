# postgresql-vacuum-analyze

**Issue:** Understanding and tuning autovacuum to prevent table bloat and transaction ID wraparound
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tables grow in size even when rows are deleted because PostgreSQL uses MVCC — dead tuples accumulate. Autovacuum falls behind on write-heavy tables, causing query slowdowns, index bloat, and eventually transaction ID wraparound (which shuts down the entire cluster).

## Pattern / Solution
Monitor bloat and tune autovacuum per table for high-churn workloads.

**Check bloat and dead tuple counts:**
```sql
-- Tables with most dead tuples
SELECT relname, n_dead_tup, n_live_tup,
       round(n_dead_tup::numeric / nullif(n_live_tup + n_dead_tup, 0) * 100, 1) AS dead_pct,
       last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;

-- Transaction ID age (must stay < 2 billion)
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
-- Alert if xid_age > 1.5 billion
```

**Run vacuum manually when autovacuum is behind:**
```sql
-- Non-locking vacuum + analyze
VACUUM ANALYZE orders;

-- Full rewrite (locks table, reclaims disk space)
VACUUM FULL orders;  -- use only during maintenance window

-- Freeze old transactions (prevents wraparound)
VACUUM FREEZE orders;
```

**Tune autovacuum for a high-churn table:**
```sql
ALTER TABLE events SET (
  autovacuum_vacuum_scale_factor     = 0.01,   -- vacuum when 1% rows are dead (default 0.2)
  autovacuum_analyze_scale_factor    = 0.005,  -- analyze when 0.5% rows changed
  autovacuum_vacuum_cost_delay       = 2,      -- ms (lower = more aggressive, default 20)
  autovacuum_vacuum_cost_limit       = 800     -- work units per delay (default 200)
);
```

**postgresql.conf global tunables:**
```
autovacuum_max_workers     = 5        # default 3; increase for many databases
autovacuum_naptime         = 30s      # check interval (default 1 min)
vacuum_cost_delay          = 2ms      # global I/O throttle
```

## Gotchas
- `VACUUM FULL` acquires an `AccessExclusiveLock` — the table is completely unavailable during the operation; use `pg_repack` for online repack.
- Long-running transactions prevent vacuum from removing dead tuples newer than the transaction's snapshot — identify with `SELECT * FROM pg_stat_activity WHERE state != 'idle' ORDER BY xact_start;`.
- `autovacuum_vacuum_cost_delay = 0` disables throttling; on SSDs this is often fine, but it competes with production I/O.
- Partitioned tables need vacuum on each partition individually; the parent table's `pg_stat_user_tables` row shows zeros.

## Related
- `postgresql-connection-pooling-pgbouncer.md`
- `postgresql-backup-restore.md`
- `postgresql-17-18-best-practices.md`
