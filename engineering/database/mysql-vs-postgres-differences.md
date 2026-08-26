# mysql-vs-postgres-differences

**Issue:** Developers switching between MySQL and Postgres encounter subtle behavioral differences
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Query works in MySQL but fails or returns different results in Postgres. Schema migration scripts use MySQL syntax incompatible with Postgres.

## Pattern / Solution
Key differences: Postgres case-sensitive for identifiers (use lowercase). Postgres uses SERIAL/BIGSERIAL or GENERATED ALWAYS AS IDENTITY; MySQL uses AUTO_INCREMENT. Postgres BOOLEAN is true type; MySQL uses TINYINT(1). String functions differ: IFNULL vs COALESCE, GROUP_CONCAT vs string_agg.

## Gotchas
- MySQL allows SELECT col FROM t GROUP BY other_col without aggregate; Postgres rejects it
- MySQL auto-commits DDL; Postgres wraps DDL in transactions (rollbackable)
- Postgres JSON has jsonb (indexable); MySQL has JSON type without GIN indexing

## Related
- schema-design-principles
- transaction-isolation-levels
- normalization-denormalization-tradeoffs
