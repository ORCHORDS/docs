# debezium-cdc-patterns

**Issue:** Debezium CDC setup, offset management, and schema evolution cause operational issues
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Debezium connector restarting from the beginning after downtime, replaying millions of events. Schema change in Postgres breaking Debezium connector.

## Pattern / Solution
Debezium reads Postgres WAL via logical replication. Key configuration: plugin.name = pgoutput (built-in, no extension needed in PG10+). Offset stored in Kafka -- connector resumes from last committed offset. Schema registry for Avro serialization with evolution support.

## Gotchas
- snapshot.mode = initial replays full table on first start -- use never if downstream can bootstrap another way
- Adding nullable columns is backward-compatible; dropping/renaming columns breaks consumers
- heartbeat.interval.ms keeps slot active during low-traffic periods, preventing WAL accumulation

## Related
- database-change-data-capture
- redis-streams
- eventual-consistency-patterns
