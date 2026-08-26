# PostgreSQL pg_stat_wal generation-rate diagnostics

**Issue:** Storage growth and replication lag can be driven by changing WAL generation, but checkpoint counts or database write throughput alone do not identify WAL volume and full-page-image amplification.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Collect `pg_stat_wal` counters as rates and retain the `stats_reset` timestamp. Track `wal_bytes`, `wal_records`, `wal_fpi`, buffer-full events, write/sync counts, and write/sync time where timing is enabled. Correlate them with checkpoints, workload releases, replication lag, archive throughput, and remaining storage. Base alerts on sustained generation versus demonstrated archival and replication capacity.

## Verification

Run a bounded staging workload, record a baseline, reset statistics only in the test environment, and confirm computed rates match observed WAL file creation. Exercise a checkpoint-heavy case to observe full-page-image behavior. Verify dashboards handle restart or reset without negative or inflated rates and that storage alerts fire before exhaustion.

## Gotchas

Counters are cumulative and lose meaning when divided across an unobserved reset. `track_wal_io_timing` adds timing visibility but can impose platform-dependent overhead. WAL compression and full-page-write settings change the relationship between transactions and bytes; do not weaken durability to improve a graph.

## Official sources

- https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-WAL-VIEW
- https://www.postgresql.org/docs/current/wal-configuration.html
- https://www.postgresql.org/docs/current/runtime-config-wal.html
