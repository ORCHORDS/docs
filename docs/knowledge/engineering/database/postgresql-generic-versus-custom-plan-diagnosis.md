# PostgreSQL generic-versus-custom plan diagnosis

**Issue:** Parameter-sensitive queries can become slow when a reusable generic plan is poor for skewed values, while forcing custom planning adds repeated planning cost.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

PostgreSQL normally chooses between custom and generic cached plans automatically. Diagnose with representative parameters before using `plan_cache_mode`; forced modes are experiments or narrowly scoped mitigations, not universal tuning.

## Controls and verification

- Compare `EXPLAIN (ANALYZE, BUFFERS)` for common, rare, and boundary parameter values.
- Include planning time, execution time, row-estimate error, and buffer use.
- Scope overrides to a session or affected workload where possible.
- Reassess statistics and indexes before forcing a mode.
- Load-test connection-pool prepared-statement behavior.
- Remove the override if distribution or PostgreSQL version changes invalidate the evidence.

## Sources

- [PostgreSQL 18: Query planning configuration](https://www.postgresql.org/docs/current/runtime-config-query.html)
- [PostgreSQL 18: PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html)
