# PostgreSQL MERGE RETURNING action audit

**Issue:** Bulk synchronization can change rows through several actions while the application guesses which rows were inserted, updated, or deleted.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

On a PostgreSQL version that supports it, make the result contract explicit with `MERGE ... RETURNING merge_action()` plus only the source and target fields needed for reconciliation. Remember that the first true `WHEN` clause wins for each candidate row and that privilege checks cover every action named by the statement, even when a branch is not taken. Treat `DO NOTHING` rows as separately accounted input because they do not represent an inserted, updated, or deleted result row.

Keep the join condition limited to target identity. Put action filters in their `WHEN` clauses, prevent multiple source rows from ambiguously targeting one row, and consume returned rows in the same transaction as downstream audit bookkeeping.

## Verification

Exercise matched update, matched delete, not-matched insert, guarded no-op, duplicate source identity, trigger effects, and rollback. Reconcile source, changed, skipped, and rejected counts; assert the returned action label and old/new values required by the audit contract.

## Gotchas

- `RETURNING` reports database actions; it does not make a non-idempotent source safe to replay.
- Triggers and concurrent transactions can change observable results.
- Pin tests to the deployed PostgreSQL major version.

## Official source

- [PostgreSQL MERGE](https://www.postgresql.org/docs/current/sql-merge.html)
