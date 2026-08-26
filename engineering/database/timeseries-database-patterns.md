# timeseries-database-patterns

**Issue:** General-purpose databases struggle with time-series data ingestion and retention patterns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
High-frequency sensor/metric data at 10k+ writes/sec. Queries always filter by time range. Data older than 90 days never queried.

## Pattern / Solution
Purpose-built options: TimescaleDB (Postgres-compatible), InfluxDB, Prometheus (pull model), VictoriaMetrics (Prometheus-compatible, higher compression). Common patterns: continuous rollups (raw to 1min to 1hr to 1day), automatic retention with TTL, chunk/segment by time for fast deletes.

## Gotchas
- Cardinality explosion: each unique label combination is a separate series -- high cardinality kills Prometheus/InfluxDB
- For low-frequency data (<1000/sec) Postgres + TimescaleDB is often simpler than dedicated TSDB
- Downsampling loses precision -- define retention/resolution policy before ingestion begins

## Related
- timescaledb-time-series
- clickhouse-analytics
- data-retention-deletion
