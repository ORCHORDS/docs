# database-sharding-strategies

**Issue:** Single database cannot handle data volume or write throughput at scale
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Postgres primary at 70%+ capacity, writes bottlenecked, table sizes in hundreds of GB slowing queries even with good indexes.

## Pattern / Solution
Horizontal sharding splits data across multiple database instances by a shard key. Common strategies: hash sharding (even distribution), range sharding (good for time-series), directory sharding (lookup table maps key to shard, flexible). Shard key must be in every query to avoid cross-shard scatter.

## Gotchas
- Cross-shard joins require application-level merging or denormalization
- Resharding is expensive; choose shard count with growth in mind
- Hotspots: if shard key has skewed distribution one shard gets overloaded

## Related
- horizontal-partitioning
- table-partitioning-postgres
- distributed-transactions-saga
