# SQLite STRICT tables and ANY type contract

**Issue:** SQLite affinity can accept a value under a storage class the application did not intend, while an indiscriminate rigid schema can also destroy identifiers whose lexical form matters.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Declare `STRICT` per table when the schema requires lossless type enforcement. In a STRICT table, use only the supported type names (`INT`, `INTEGER`, `REAL`, `TEXT`, `BLOB`, and `ANY`) and reserve `ANY` for values whose exact SQLite type and representation must be preserved. A value that cannot be losslessly coerced to a non-ANY column fails with `SQLITE_CONSTRAINT_DATATYPE`.

Gate migrations on every reader and writer using SQLite 3.37 or later. Run `PRAGMA integrity_check` or `quick_check` as an independent type-integrity check, and keep identifier tests such as text `000123` so a later schema change cannot normalize away meaningful zeros.

## Verification

Test valid values, lossless coercions, rejected coercions, NULL constraints, `INTEGER PRIMARY KEY`, and ANY values across dump/restore and every shipped SQLite library. Open a migrated fixture with the oldest supported application before rollout.

## Gotchas

- STRICT changes type enforcement, not foreign-key, uniqueness, or CHECK semantics.
- `ANY` behaves differently in strict and ordinary tables.
- The file format is compatible, but older SQLite parsers do not understand the STRICT table option safely for normal use.

## Official source

- [SQLite STRICT tables](https://www.sqlite.org/stricttables.html)
