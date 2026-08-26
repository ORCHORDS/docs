# d1-column-affinity-gotcha

**Issue:** SQLite (D1) column type affinity causes unexpected implicit type coercions when inserting or querying typed values
**Date:** 2026-08-11
**Status:** documented

## Symptom
A value stored as `"123"` (string) in a column declared `INTEGER` is returned as `123` (number). Or a boolean `true` stored in a `TEXT` column comes back as `1`. Strict type comparisons in application code fail.

## Root cause
SQLite uses dynamic typing with type affinity rules. A column declared `INTEGER` will try to coerce stored values to integers. `TEXT` columns store the string representation of any value. There is no native `BOOLEAN` or `UUID` type — these are stored as `INTEGER` (0/1) or `TEXT`.

## Fix
1. Be explicit about the SQLite type affinity you intend.
2. For booleans, store and compare as `0`/`1` integers:
```sql
CREATE TABLE flags (id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0);
```
3. For UUIDs, store as `TEXT` and always query with string comparisons.
4. Validate types in the application layer with zod or valibot after reading from D1.

## Detection
```
grep -rn "BOOLEAN\|BOOL\|UUID" schema.sql migrations/
```
Replace with `INTEGER` (boolean) or `TEXT` (UUID).

## Related
- `d1-integer-overflow-javascript.md`
- `d1-env-type-incompatibility.md`
