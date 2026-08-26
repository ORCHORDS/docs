# PostgreSQL `pg_stat_io` interpretation and baselining

**Issue:** Teams treat one cache-hit percentage as a database health verdict, then miss checkpoint, WAL, or backend-specific I/O pressure.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use `pg_stat_io` as a cluster-wide I/O evidence source, segmented by backend type, context, and target. Pair it with operating-system or storage telemetry; do not interpret it as physical-disk I/O or as a per-query trace.

## Why it matters

PostgreSQL records much more than table reads: checkpointer, background writer, WAL, autovacuum, client backend, and other backend classes can have distinct failure modes. `pg_stat_io` counters help isolate where reads, writes, extends, fsyncs, and their timings are accumulating.

## Safe operating method

1. Establish a baseline for normal workload windows before alerting.
2. Enable and assess `track_io_timing` / `track_wal_io_timing` deliberately, accounting for their query-execution overhead.
3. Compare time-series deltas, not counters from a single instant; counters can reset after an unclean shutdown.
4. Break panels down by backend type, context, and object target, then correlate with checkpoints, WAL volume, latency, saturation, and query workload.
5. Query cumulative statistics outside long-lived transactions, or deliberately refresh the statistics snapshot, to avoid reading cached values.
6. Restrict access to detailed statistics: ordinary roles cannot see all session data.

## Limits and checks

- PostgreSQL statistics are not instantaneous; per-process updates can lag.
- The views capture most kernel I/O calls but cannot distinguish data fetched from storage from data already present in the kernel page cache.
- A rising cache-hit ratio can coexist with a serious WAL/fsync or checkpoint problem.
- Validate a panel during a controlled workload and compare its interpretation with host-level I/O telemetry before making it a paging signal.

## Sources

- [PostgreSQL 18: cumulative statistics system](https://www.postgresql.org/docs/current/monitoring-stats.html)
