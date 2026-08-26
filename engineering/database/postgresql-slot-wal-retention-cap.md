# PostgreSQL replication-slot WAL retention cap

**Issue**

An inactive replication slot can retain WAL until storage is exhausted unless retention is bounded.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `max_slot_wal_keep_size` from recovery and disk budgets.
- Monitor slot lag, WAL bytes, and invalidation state.
- Coordinate consumer recovery before raising the cap.

## Verification

1. Stop consumers until below and beyond the cap.
2. Verify alerts precede invalidation or disk pressure.
3. Test restart and archive interaction.

## Gotchas

- A capped slot may become unusable for lagged consumers.
- Checkpoint timing affects enforcement.
- Physical and logical recovery differ.

## Official source

- [Official documentation](https://www.postgresql.org/docs/current/runtime-config-replication.html)
