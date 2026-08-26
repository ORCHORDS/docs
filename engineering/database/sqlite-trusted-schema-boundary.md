# SQLite trusted-schema boundary

**Issue**

Application-defined functions used from schema objects can create unsafe execution paths when a database file is untrusted.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Disable trusted schema for untrusted database files.
- Mark safe functions innocuous and keep extension loading disabled.
- Validate schema before privileged migration.

## Verification

1. Create malicious views, triggers, generated columns, and indexes.
2. Open trusted and untrusted files through separate connection policies.
3. Verify required schemas still work.

## Gotchas

- Trusted schema is not filesystem sandboxing.
- Compatibility can break for functions used in schema.
- Connection policy must be set early.

## Official source

- [Official documentation](https://sqlite.org/pragma.html#pragma_trusted_schema)
