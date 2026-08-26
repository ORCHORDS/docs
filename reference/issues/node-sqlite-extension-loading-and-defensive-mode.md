# Node SQLite Extension Loading and Defensive Mode

**Issue:** Node’s built-in SQLite API can load extensions or expose database features that expand the attack surface. Treating a local database file as trusted can permit unsafe schema or extension behavior.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Keep extension loading disabled unless a reviewed use case requires it.
- If extensions are required, enable loading deliberately and load only an allowlisted absolute path with controlled filesystem permissions.
- Enable defensive database configuration where compatible and prohibit writable-schema style behavior.
- Open untrusted or user-supplied databases in an isolated process with resource limits.

## Verification

- Attempt to load an extension while loading is disabled.
- Replace an approved extension path and verify integrity or permission controls reject it.
- Open malformed and adversarial database files under process limits.

## Gotchas

- A parameterized SQL query does not make a malicious database file safe.
- Native extensions execute code in the database process.

## Official sources

- https://nodejs.org/api/sqlite.html
