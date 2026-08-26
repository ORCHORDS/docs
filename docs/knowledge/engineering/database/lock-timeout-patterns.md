# lock-timeout-patterns

**Issue:** Queries wait indefinitely for locks, blocking application threads
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Application threads pile up waiting for a single locked row or table-level lock. Connection pool exhausted. Common during schema migrations that take an ACCESS EXCLUSIVE lock.

## Pattern / Solution
Set lock_timeout at session or transaction level: SET LOCAL lock_timeout = '5s'. Application catches lock timeout error (55P03) and retries or returns 503. For migrations, loop with short lock_timeout until acquired.

## Gotchas
- lock_timeout only applies to waiting for a lock, not to query execution time
- Migrations that rewrite tables hold ACCESS EXCLUSIVE for the entire rewrite -- use pg_repack instead
- NOWAIT flag in SELECT FOR UPDATE fails immediately -- useful for try-lock patterns
- SET LOCAL applies only within current transaction

## Related
- deadlock-detection-prevention
- zero-downtime-migrations
- connection-limit-management
