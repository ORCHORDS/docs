# postgresql-replication-lag

**Issue:** Monitoring and reducing streaming replication lag on PostgreSQL standbys
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Read queries routed to a standby return stale data. Failover to a lagging standby causes data loss. Lag grows during bulk inserts or autovacuum on the primary.

## Pattern / Solution
Monitor lag in bytes and seconds, and tune replication to minimize it.

**Check replication lag on the primary:**
```sql
-- Lag in bytes and estimated seconds
SELECT
  client_addr,
  state,
  sent_lsn,
  write_lsn,
  flush_lsn,
  replay_lsn,
  (sent_lsn - replay_lsn) AS replay_lag_bytes,
  write_lag,
  flush_lag,
  replay_lag
FROM pg_stat_replication;
```

**Check lag on the standby:**
```sql
SELECT
  now() - pg_last_xact_replay_timestamp() AS replication_lag_seconds,
  pg_is_in_recovery() AS is_standby,
  pg_last_wal_replay_lsn() AS last_replayed_lsn;
```

**Prometheus exporter metrics (postgres_exporter):**
```
# Alert: lag > 30 seconds
pg_replication_lag > 30
# Alert: standby not streaming
pg_replication_is_replica == 0
```

**Causes of high lag and remedies:**

| Cause | Remedy |
|-------|--------|
| Network saturation | Move standby to same AZ; enable WAL compression (`wal_compression = lz4`) |
| Standby disk I/O | Use faster storage; tune `recovery_min_apply_delay` to 0 |
| Hot standby conflict | Tune `max_standby_streaming_delay` and `hot_standby_feedback = on` |
| Autovacuum anti-wraparound | Schedule during low traffic; increase `autovacuum_freeze_max_age` |

**Synchronous replication for zero data loss:**
```
# postgresql.conf on primary
synchronous_commit = on
synchronous_standby_names = 'FIRST 1 (standby1, standby2)'
# Trades write latency for durability guarantee
```

## Gotchas
- `hot_standby_feedback = on` prevents the primary from vacuuming rows the standby is still reading, which can cause bloat on the primary.
- Replication slots on an unused standby accumulate WAL indefinitely and can fill the disk — monitor `pg_replication_slots` and drop unused slots.
- `synchronous_commit = remote_write` is a middle ground: faster than `on`, still protects against standby crash.
- Cascading replication (standby of a standby) multiplies lag; avoid it for low-latency failover targets.

## Related
- `postgresql-connection-pooling-pgbouncer.md`
- `postgresql-backup-restore.md`
- `prometheus-alertmanager-config.md`
