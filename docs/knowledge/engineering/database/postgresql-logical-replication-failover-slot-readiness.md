# PostgreSQL Logical-Replication Failover Slot Readiness

**Issue:** Promoting a physical standby does not by itself guarantee that logical subscribers can resume; required logical slots may be absent, temporary, invalid, or behind the subscriber.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

- Create or alter the logical subscription/slot with failover enabled.
- Configure a physical slot for the standby, `hot_standby_feedback`, and `sync_replication_slots` on the standby according to the supported PostgreSQL release.
- Use `synchronized_standby_slots` where required so logical decoding does not advance beyond WAL confirmed by the designated physical standby.
- Before planned promotion, inventory every failover-enabled subscription slot and completed table-synchronization slot.
- On the candidate standby, require each needed row in `pg_replication_slots` to satisfy `synced AND NOT temporary AND invalidation_reason IS NULL`.
- Disable subscribers during a controlled cutover, promote, change subscription connection information to the new primary, and then re-enable.

## Readiness gate

Fail the promotion gate if a required slot is missing, not persistent, invalidated, or if the standby is behind the subscriber. Monitor retained WAL and catalog horizons because an abandoned slot can consume storage and prevent cleanup. Treat manual `pg_sync_replication_slots()` as a controlled operation, not a substitute for continuous synchronization.

## Verification drill

1. Generate writes through the publisher and record an application-level sequence or immutable event identifier.
2. Confirm slot readiness on the standby.
3. Promote in a disposable environment.
4. Point the subscriber at the new primary.
5. Prove continuity: no missing identifiers, understood duplicate behavior, and decreasing apply lag.
6. Exercise rollback and document when the old primary may safely rejoin.

## Gotchas

Synchronization is asynchronous. Seeing a slot name is insufficient; its state matters. Losing required WAL or catalog rows can invalidate synchronization. Retained WAL needs an alert and capacity limit. Test with the exact PostgreSQL major version because failover-slot capabilities evolved across releases.

## Sources

- [PostgreSQL logical replication failover](https://www.postgresql.org/docs/current/logical-replication-failover.html)
- [PostgreSQL logical decoding and slot synchronization](https://www.postgresql.org/docs/current/logicaldecoding-explanation.html)
- [PostgreSQL replication settings](https://www.postgresql.org/docs/current/runtime-config-replication.html)
