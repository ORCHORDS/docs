# PostgreSQL idle-transaction timeout and connection hygiene

**Issue:** Sessions left idle inside transactions retain snapshots and locks, interfering with vacuum, schema changes, and other sessions.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

PostgreSQL `idle_in_transaction_session_timeout` terminates sessions that remain idle while a transaction is open. Set it from application behavior and operational risk, preferably by role or workload before using a broad global value.

This setting is not a query runtime limit. Coordinate it with `statement_timeout`, `lock_timeout`, pool settings, and application retry behavior.

## Controls

- Fix transaction lifecycle bugs before relying on termination.
- Exempt only reviewed administrative workflows.
- Ensure clients handle terminated sessions and discard broken pooled connections.
- Monitor idle transaction age and held locks.
- Roll out gradually.
- Keep migration tooling under explicit timeout policy.

## Verification

1. Open an idle transaction and confirm termination after the configured interval.
2. Verify locks and snapshots are released.
3. Confirm a legitimately active statement is governed separately.
4. Exercise connection-pool recovery.
5. Observe vacuum and DDL behavior before and after.

## Sources

- [PostgreSQL 18: Client connection defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [PostgreSQL 18: Monitoring database activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
