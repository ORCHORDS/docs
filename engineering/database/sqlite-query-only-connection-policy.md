# SQLite query-only connection policy

**Issue**

Read paths can accidentally mutate application databases through pragmas, temporary assumptions, or reused connections.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable `PRAGMA query_only` on reader connections.
- Keep writer pools separate and observable.
- Still enforce filesystem and schema trust.

## Verification

1. Attempt DML, DDL, temp writes, and reads.
2. Test pool reset and transaction reuse.
3. Verify expected failures propagate.

## Gotchas

- Query-only is connection-local.
- It is not an authorization sandbox.
- Some temporary operations have distinct behavior.

## Official source

- [Official documentation](https://sqlite.org/pragma.html#pragma_query_only)
