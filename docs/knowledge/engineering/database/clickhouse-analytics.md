# clickhouse-analytics

**Issue:** Postgres or MySQL cannot sustain analytical query performance at hundreds of millions of rows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Reporting queries running for minutes against large event/log tables. Need sub-second aggregations over billions of rows.

## Pattern / Solution
ClickHouse is a columnar OLAP database optimized for fast aggregations. Key concepts: MergeTree engine (primary key is sparse index, not unique), ORDER BY defines physical sort and primary index, PARTITION BY for data management. Materialized views for pre-aggregation.

## Gotchas
- ClickHouse is append-optimized -- updates and deletes are async and expensive (mutation)
- No transactions -- eventual consistency between mutations and reads
- JOINs are less optimized than Postgres -- prefer denormalized schemas
- Small inserts (<1000 rows) create many small parts -- batch inserts or use Buffer table engine

## Related
- timeseries-database-patterns
- cqrs-read-write-split
- database-sharding-strategies
