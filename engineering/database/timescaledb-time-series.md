# timescaledb-time-series

**Issue:** Postgres performance degrades on append-heavy time-series workloads at scale
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Metrics/events table growing to billions of rows. INSERT throughput degrading. Range queries on time column slow despite partitioning.

## Pattern / Solution
TimescaleDB extends Postgres with hypertables (automatic time-based chunking), continuous aggregates (materialized rollups updated incrementally), and compression (columnar, 90%+ ratio). Convert existing table: SELECT create_hypertable('metrics', 'time'). Query syntax is standard SQL.

## Gotchas
- TimescaleDB community edition is Apache 2.0; advanced features require paid license
- Chunk size default (7 days) may need tuning for high-frequency data
- Continuous aggregates have refresh lag; real-time aggregates add overhead

## Related
- table-partitioning-postgres
- timeseries-database-patterns
- postgres-extensions-useful
