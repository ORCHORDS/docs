# PostgreSQL idle replication slot timeout operations

**Issue:** Abandoned replication slots can retain WAL indefinitely and exhaust disk when no consumer advances them.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

For supported PostgreSQL versions, set `idle_replication_slot_timeout` from recovery objectives and realistic maintenance windows. Monitor `pg_replication_slots`, retained WAL, activity, and invalidation reasons; alert well before timeout or disk pressure. Maintain an explicit exemption or recreation runbook for intentionally dormant consumers.

## Verification

Create a disposable inactive slot, force checkpoint behavior as documented, and verify invalidation timing and reason without risking production slots. Exercise consumer recovery or controlled resynchronization after invalidation.

## Gotchas

Invalidation is enforced at checkpoints and may occur later than the nominal timeout. Invalidating a slot can require subscriber resynchronization and cause data gaps if the consumer cannot recover.

## Official sources

- https://www.postgresql.org/docs/current/runtime-config-replication.html
- https://www.postgresql.org/docs/current/view-pg-replication-slots.html
