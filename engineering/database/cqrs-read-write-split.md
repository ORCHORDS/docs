# cqrs-read-write-split

**Issue:** Single data model cannot efficiently serve both write operations and complex read queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Reporting queries slow down OLTP. Write model optimized for consistency but read model needs denormalized views. Adding indexes for reads hurts write performance.

## Pattern / Solution
CQRS: separate write model (normalized, transactional) from read model (denormalized, optimized for specific queries). Sync via events or CDC. Read model can be materialized views, separate tables, Elasticsearch index, or Redis cache.

## Gotchas
- Synchronization lag between write and read models must be acceptable for the use case
- Operational complexity doubles -- two models to maintain and sync
- Start with simpler patterns (read replicas, materialized views) before full CQRS

## Related
- read-replicas-routing
- database-change-data-capture
- eventual-consistency-patterns
