# PostgreSQL commit-timestamp tracking

**Problem**

Tracking commit timestamps adds shared-memory/WAL work and creates retention semantics that applications can mistake for immutable business time.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only for replication/audit tooling that explicitly needs transaction commit time.

## Controls

- Enable cluster-wide after measuring overhead.
- Treat values as database metadata, not legal event timestamps.
- Plan upgrade and retention behavior.

## Implementation

- Canary and query supported commit timestamp functions.
- Keep application event time separate.
- Document fallback when timestamps are unavailable.

## Tests

- Test old/new transactions, restart, replica, failover, and disable/re-enable.

## Gotchas

- Historical coverage is bounded.
- System clocks can move.
- Feature changes require restart/config lifecycle.

## Official sources

- [Official documentation](https://www.postgresql.org/docs/current/runtime-config-replication.html)
