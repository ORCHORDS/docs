# SQLite PRAGMA optimize maintenance budget

**Issue**

Planner statistics maintenance should be bounded and demand-driven rather than running an unbounded ANALYZE on every connection.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run `PRAGMA optimize` after opening long-lived connections and before controlled close points.
- Use the recommended optimize mask only after validating the deployed SQLite version.
- Persist the database file normally; never copy it while a write transaction is active.

## Verification

1. Test fresh, stale, and large statistics tables.
2. Capture query plans before and after representative data shifts.
3. Measure maintenance latency under the production busy timeout.

## Gotchas

- Optimize may be a no-op when analysis is unnecessary.
- Behavior evolves with SQLite releases.
- Statistics improve estimates, not query correctness.

## Official source

- [Official documentation](https://sqlite.org/pragma.html#pragma_optimize)
