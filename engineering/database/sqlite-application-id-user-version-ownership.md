# SQLite application_id and user_version ownership contract

**Issue:** An application can open the wrong SQLite file or run an incompatible schema because the database header is treated as anonymous and migration state is inferred from tables alone.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Assign a registered, stable `PRAGMA application_id` when SQLite is used as an application file format. Check it before interpreting application tables.
- Reserve `PRAGMA user_version` for the application's monotonically managed schema version. SQLite stores the integer but does not interpret or advance it.
- Change schema and `user_version` in the same reviewed migration transaction, then verify both before commit. Keep a separate immutable migration history for checksums and downgrade policy.
- Fail closed on an unknown application ID or a version newer than the binary supports. Route older supported versions through explicit, idempotent migrations.
- Do not write `schema_version`; SQLite owns that internal value and may invalidate prepared statements when it changes.

## Verification

Test an empty file, a different product's SQLite file, every supported old version, a future version, an interrupted migration, and a copied database with valid tables but the wrong application ID. Reopen the file after migration and assert both header values and schema invariants.

## Gotchas

- Both fields are integers, not authentication or tamper evidence.
- `user_version` cannot replace a migration ledger or content validation.
- Cloning a file clones these values too; provenance still needs an external control.

## Official source

- [SQLite PRAGMA application_id and user_version](https://www.sqlite.org/pragma.html#pragma_application_id)
