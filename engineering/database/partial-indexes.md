# partial-indexes

**Issue:** Creating indexes that cover only a subset of rows for efficiency
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A full-table index on a column where 99% of queries only touch active/non-deleted rows wastes space and slows writes.

## Pattern / Solution
```sql
-- Index only active users
CREATE INDEX idx_users_email_active
  ON users (email)
  WHERE deleted_at IS NULL;

-- Index only unprocessed jobs
CREATE INDEX idx_jobs_pending
  ON jobs (created_at)
  WHERE status = ''pending'';

-- Unique constraint on active rows only
CREATE UNIQUE INDEX uq_slugs_active
  ON posts (slug)
  WHERE published = true;
```

## Gotchas
- The query WHERE clause must match the index predicate exactly for Postgres to use it
- Partial indexes are not portable to all databases (MySQL lacks them)
- Can have many partial indexes on the same column for different predicates

## Related
- `covering-indexes.md`
- `index-selectivity.md`
- `soft-delete-schema-design.md`
