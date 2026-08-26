# PostgreSQL CREATE INDEX progress and blocker triage

**Issue:** Long-running index builds are often treated as opaque jobs, causing unsafe cancellation or missed lock and snapshot blockers.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use PostgreSQL's `pg_stat_progress_create_index` view to observe each active `CREATE INDEX` or `REINDEX` operation. Treat `phase` as the primary state signal rather than assuming that elapsed time alone means the build is stuck.

For phases that process data, compare `blocks_done` with `blocks_total` or `tuples_done` with `tuples_total` only when those totals are populated. For wait phases, inspect `lockers_total`, `lockers_done`, and `current_locker_pid`, then correlate the PID with `pg_stat_activity`. Concurrent builds can legitimately wait for writers, validation, old snapshots, or readers.

## Operational controls

- Record phase changes and progress counters at a bounded interval; do not poll so aggressively that monitoring becomes load.
- Alert separately on a non-advancing build phase and on a wait phase with an identified blocker.
- Confirm the target relation and index OIDs before terminating any backend.
- Prefer resolving an abandoned transaction or old snapshot over blindly cancelling the index builder.
- After interruption, verify index validity before retrying. A failed concurrent build can leave an invalid index that needs deliberate cleanup.

## Verification

1. Start the index operation in a controlled environment.
2. Query `pg_stat_progress_create_index` and confirm the expected command, relation, and phase.
3. Simulate or identify a blocker and confirm `current_locker_pid` correlates with `pg_stat_activity`.
4. After completion, confirm no progress row remains and verify the index is valid and used by an appropriate query plan.

## Sources

- [PostgreSQL 18: Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html)
- [PostgreSQL 18: CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html)
