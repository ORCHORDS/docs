# two-phase-commit

**Issue:** Coordinating commits across multiple resource managers without losing atomicity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Financial systems needing atomic commits across Postgres and a message broker, or two separate Postgres instances.

## Pattern / Solution
Phase 1 (prepare): coordinator asks all participants to prepare and durably record intent. Phase 2 (commit): if all prepared, coordinator sends commit. Postgres supports PREPARE TRANSACTION and COMMIT PREPARED. Coordinator must recover from crashes by querying pg_prepared_xacts.

## Gotchas
- 2PC is blocking -- if coordinator crashes after prepare but before commit, participants hold locks until recovery
- Prepared transactions hold locks indefinitely; monitor pg_prepared_xacts for orphans
- max_prepared_transactions GUC must be set > 0 in Postgres (default 0 disables 2PC)

## Related
- distributed-transactions-saga
- transaction-isolation-levels
- savepoints-nested-transactions
