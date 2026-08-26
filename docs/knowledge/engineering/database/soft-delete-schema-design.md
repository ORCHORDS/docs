# soft-delete-schema-design

**Issue:** Implementing logical deletes without physically removing rows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hard deletes lose audit history and break FK references; soft deletes preserve data but complicate queries.

## Pattern / Solution
```sql
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMPTZ;

-- Partial index to exclude deleted rows from common queries
CREATE INDEX idx_users_active ON users (email) WHERE deleted_at IS NULL;

-- Unique constraint only on active rows
CREATE UNIQUE INDEX uq_users_email_active ON users (email) WHERE deleted_at IS NULL;

-- Always filter in queries
SELECT * FROM users WHERE deleted_at IS NULL;

-- Row-level security alternative
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY active_only ON users USING (deleted_at IS NULL);
```

## Gotchas
- Every query must include `WHERE deleted_at IS NULL` — easy to forget
- FKs can still point to soft-deleted rows; add CHECK or trigger to prevent this
- Indexes bloat with deleted rows; consider periodic hard-delete of old soft-deleted records

## Related
- `partial-indexes.md`
- `row-level-security.md`
- `audit-columns-pattern.md`
