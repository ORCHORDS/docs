# pagination-offset-vs-cursor

**Issue:** Choosing between OFFSET and cursor-based pagination
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
OFFSET pagination becomes slower as the page number grows (must scan all preceding rows) and can miss or duplicate rows when data changes.

## Pattern / Solution
```sql
-- OFFSET (simple but slow at high pages)
SELECT * FROM posts ORDER BY created_at DESC LIMIT 20 OFFSET 200;

-- Cursor-based (fast, stable)
-- First page
SELECT * FROM posts ORDER BY created_at DESC, id DESC LIMIT 20;

-- Subsequent pages (use last row''s values as cursor)
SELECT * FROM posts
WHERE (created_at, id) < ($last_created_at, $last_id)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

## Gotchas
- Cursor pagination does not support random page jumps ("go to page 10")
- The cursor columns must be in the ORDER BY and indexed as a composite
- Ties in the sort column (e.g., same created_at) require a tiebreaker like `id`

## Related
- `keyset-pagination.md`
- `composite-index-design.md`
