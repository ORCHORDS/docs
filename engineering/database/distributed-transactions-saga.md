# distributed-transactions-saga

**Issue:** ACID transactions across microservices or databases are not feasible
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Order service debits inventory, payment service charges card, shipping service creates shipment -- each has its own DB. A crash halfway leaves data inconsistent.

## Pattern / Solution
Saga pattern: sequence of local transactions with compensating transactions for rollback. Two styles: choreography (events trigger next step) and orchestration (central coordinator). On failure, publish failure event and execute compensating transaction.

## Gotchas
- Compensating transactions must be idempotent -- they may run multiple times
- Sagas are eventually consistent; interim states are visible to other requests
- Avoid sagas for tightly coupled data that should live in the same database

## Related
- two-phase-commit
- eventual-consistency-patterns
- database-change-data-capture
