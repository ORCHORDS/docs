# database-change-data-capture

**Issue:** Propagating database changes to downstream systems without polling or dual writes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cache invalidation requires knowing exactly which rows changed. Search index must reflect DB updates within seconds. Microservices need to react to data changes without tight coupling.

## Pattern / Solution
CDC reads the database transaction log (WAL in Postgres) to stream changes as events. Set wal_level = logical. Tools: Debezium (Kafka Connect source), pglogical, Postgres logical replication slots. Output: INSERT/UPDATE/DELETE events with before/after values published to Kafka or other message broker.

## Gotchas
- Replication slots retain WAL until consumer confirms -- unconsumed slot causes WAL disk to fill up
- Monitor pg_replication_slots.confirmed_flush_lsn lag
- Schema changes require careful coordination -- DDL changes to replicated tables can break consumers

## Related
- debezium-cdc-patterns
- redis-streams
- cqrs-read-write-split
