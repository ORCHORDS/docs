# PostgreSQL logical-slot failover readiness

**Issue:** Promoting a standby without synchronized logical slots can strand subscribers or risk an unsafe replication resume.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

PostgreSQL 18 supports failover-enabled logical slots synchronized to a physical standby. Configure subscriptions or slots for failover and enable `sync_replication_slots` on the standby. Synchronization is asynchronous: promotion readiness must be verified, not assumed.

## Controls and verification

- Inventory every subscriber slot, including applicable completed table-sync slots.
- Before planned promotion, require the standby slot to be synced, persistent, non-temporary, and without an invalidation reason.
- Confirm the standby is sufficiently advanced and retains required WAL/catalog state.
- Monitor slot lag and retained WAL to prevent disk exhaustion.
- Rehearse connection-string changes, subscriber disable/enable ordering, and rollback.
- Test a full failover with writes and prove continuity and absence of duplicates.

## Sources

- [PostgreSQL 18: Logical Replication Failover](https://www.postgresql.org/docs/current/logical-replication-failover.html)
- [PostgreSQL 18: Replication settings](https://www.postgresql.org/docs/current/runtime-config-replication.html)
