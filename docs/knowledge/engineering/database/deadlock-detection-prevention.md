# deadlock-detection-prevention

**Issue:** Concurrent transactions lock resources in opposite order, causing deadlocks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ERROR: deadlock detected in Postgres logs. Usually two transactions each holding a lock the other needs.

## Pattern / Solution
Enforce consistent lock ordering: always acquire locks on multiple rows/tables in the same order (e.g., by primary key ascending). Use SELECT FOR UPDATE with ORDER BY id. Application must catch deadlock errors (code 40P01) and retry.

## Gotchas
- Implicit locks from FK checks can cause deadlocks -- index the FK column on child table
- ON CONFLICT DO UPDATE takes a stronger lock than a plain insert
- Long transactions increase deadlock probability; keep transactions short

## Related
- transaction-isolation-levels
- lock-timeout-patterns
- optimistic-locking-version-column
