# PostgreSQL pg_stat_checkpointer checkpoint diagnostics

**Issue:** Frequent requested checkpoints or slow checkpoint writes can create latency spikes and WAL pressure, while aggregate database metrics hide the cause.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Collect `pg_stat_checkpointer` counters and timings as rates, correlate requested versus scheduled checkpoints with WAL volume and storage latency, and baseline after restarts or statistic resets. Alert on sustained changes rather than a single cumulative value. Review `checkpoint_timeout`, `max_wal_size`, and `checkpoint_completion_target` together and change one bounded hypothesis at a time.

## Verification

Generate a controlled write workload in staging, record checkpoint counters, write/sync time, WAL metrics, and query latency, then confirm the expected causal change after tuning. Record `stats_reset` so rate calculations do not span a reset.

## Gotchas

Statistics describe completed work, not future capacity. Aggressive checkpoint tuning can trade latency for recovery time, WAL volume, or storage usage; do not copy thresholds across hardware.

## Official sources

- https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-CHECKPOINTER-VIEW
- https://www.postgresql.org/docs/current/wal-configuration.html
