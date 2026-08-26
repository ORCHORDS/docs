# savepoints-nested-transactions

**Issue:** Partial rollback within a transaction is not possible without savepoints
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A multi-step operation where one step might fail expectably but should not abort the whole transaction.

## Pattern / Solution
Use SAVEPOINT name, then ROLLBACK TO SAVEPOINT name on failure, or RELEASE SAVEPOINT name on success. ORMs like Prisma support nested transactions via savepoints automatically.

## Gotchas
- After any error in Postgres the transaction is aborted until rollback -- savepoints must be set BEFORE the potentially failing statement
- Savepoints add overhead; do not use in tight loops without profiling
- Nested transactions in most ORMs are implemented as savepoints, not real nested transactions

## Related
- transaction-isolation-levels
- distributed-transactions-saga
- batch-update-patterns
