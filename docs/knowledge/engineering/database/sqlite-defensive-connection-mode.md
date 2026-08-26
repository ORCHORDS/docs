# SQLite defensive connection mode

**Issue**

SQLite defensive mode disables schema features that can deliberately corrupt a database when SQL execution is less trusted.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable `SQLITE_DBCONFIG_DEFENSIVE` on connections that execute non-owner SQL.
- Keep trusted schema and extension-loading policy separate.
- Pin SQLite and test required maintenance operations.

## Verification

1. Attempt writable_schema, journal manipulation, and ordinary migrations.
2. Open existing databases under defensive mode.
3. Verify failure codes are not swallowed.

## Gotchas

- Defensive mode is not a SQL sandbox.
- It does not constrain resource consumption.
- Owner migrations may require a separate trusted connection.

## Official source

- [Official documentation](https://sqlite.org/c3ref/c_dbconfig_defensive.html)
