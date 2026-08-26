# horizontal-partitioning

**Issue:** Large tables slow down even with indexes due to sequential scan overhead and bloat
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Table with 500M+ rows. Even indexed queries slow because Postgres must consider full table statistics. Vacuum takes hours. Dropping old data requires DELETE with full table scan.

## Pattern / Solution
Split rows across multiple physical tables (partitions) by range, list, or hash. Queries including the partition key benefit from pruning. Old partitions can be detached and dropped instantly.

## Gotchas
- All queries must include the partition key for pruning to work
- Unique constraints must include the partition key
- Too many partitions (>1000) slows planning

## Related
- table-partitioning-postgres
- database-sharding-strategies
- vertical-partitioning
