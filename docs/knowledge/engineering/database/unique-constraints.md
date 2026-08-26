# unique-constraints

**Issue:** Enforcing uniqueness at the database level
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Race conditions make application-level uniqueness checks unreliable under concurrent load.

## Pattern / Solution
```sql
-- Single column unique
CREATE TABLE users (email TEXT NOT NULL UNIQUE);

-- Multi-column unique
CREATE TABLE team_members (
  team_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  UNIQUE (team_id, user_id)
);

-- Partial unique index (unique only for active records)
CREATE UNIQUE INDEX uq_users_email_active
  ON users (email)
  WHERE deleted_at IS NULL;
```

## Gotchas
- A UNIQUE constraint creates an index automatically — don't add a redundant manual index
- NULLs are not equal to each other in SQL, so multiple NULLs in a UNIQUE column are allowed
- Partial unique indexes are not portable to all databases

## Related
- `partial-indexes.md`
- `upsert-on-conflict.md`
