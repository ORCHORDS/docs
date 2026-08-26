# transaction-isolation-levels

**Issue:** Wrong isolation level causes phantom reads, dirty reads, or excessive lock contention
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Balance inconsistencies or lost updates in concurrent workloads. Or extreme slowness due to serializable isolation on a write-heavy table.

## Pattern / Solution
Postgres levels: READ COMMITTED (default), REPEATABLE READ, SERIALIZABLE. Use SET TRANSACTION ISOLATION LEVEL SERIALIZABLE for financial critical paths. Use read committed for most OLTP with application-level optimistic locking.

## Gotchas
- Postgres READ UNCOMMITTED is silently upgraded to READ COMMITTED
- Serializable failures return error code 40001 -- must retry in application code
- Serializable throughput can drop 30-50% under high contention

## Related
- deadlock-detection-prevention
- optimistic-locking-version-column
- savepoints-nested-transactions
