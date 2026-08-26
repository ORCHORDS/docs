# covering-indexes

**Issue:** Using INCLUDE columns to satisfy queries without heap access
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Even with an index hit, Postgres does a heap fetch to get non-indexed columns. A covering index eliminates this.

## Pattern / Solution
```sql
-- Without covering index: heap fetch needed for email
CREATE INDEX idx_users_id ON users (id);

-- With covering index: query satisfied from index alone
CREATE INDEX idx_users_id_covering
  ON users (id)
  INCLUDE (email, full_name);

-- Query that benefits
SELECT email, full_name FROM users WHERE id = $1;
-- EXPLAIN shows "Index Only Scan"
```

## Gotchas
- INCLUDE columns increase index size; only include frequently fetched columns
- INCLUDE is only for non-key columns — key columns already cover themselves
- An Index Only Scan requires the heap''s visibility map to be up to date; needs VACUUM

## Related
- `composite-index-design.md`
- `explain-analyze-reading.md`
