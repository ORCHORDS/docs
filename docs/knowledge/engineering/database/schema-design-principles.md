# schema-design-principles

**Issue:** Core principles for designing relational database schemas
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Poor schema design leads to data anomalies, hard-to-maintain code, and performance problems that compound over time.

## Pattern / Solution
```sql
-- Name tables as plural nouns, columns as singular descriptive names
-- Use consistent naming conventions
CREATE TABLE users (
  id          BIGSERIAL PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  full_name   TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Separate concerns: don't store derived data if it can be computed cheaply
-- Store atomic values — don't pack multiple facts into one column
```

## Gotchas
- Avoid EAV (entity-attribute-value) patterns; they kill query performance and type safety
- Never store comma-separated lists in a single column — use junction tables
- Don't prefix table names with `tbl_` or column names with the table name
- Resist over-normalization for read-heavy workloads

## Related
- `normalization-denormalization-tradeoffs.md`
- `audit-columns-pattern.md`
