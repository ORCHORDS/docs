# keyset-pagination

**Issue:** Implementing stable, performant pagination using keyset (seek) method
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cursor pagination with a single column is fragile; keyset pagination with a composite key handles all edge cases.

## Pattern / Solution
```sql
-- Schema: composite index for keyset
CREATE INDEX idx_posts_paginate ON posts (published_at DESC, id DESC);

-- Page query using ROW comparison (clean syntax)
SELECT id, title, published_at
FROM posts
WHERE (published_at, id) < ($cursor_published_at::timestamptz, $cursor_id::bigint)
ORDER BY published_at DESC, id DESC
LIMIT $page_size;

-- TypeScript helper
function buildCursor(row: { publishedAt: Date; id: number }) {
  return Buffer.from(JSON.stringify([row.publishedAt, row.id])).toString(''base64url'');
}
```

## Gotchas
- ROW comparison `(a, b) < ($1, $2)` is supported in PostgreSQL but not MySQL < 8.0
- The sort columns must be included in the SELECT to build the next cursor
- Ascending + descending mixed sorts require more complex WHERE clauses

## Related
- `pagination-offset-vs-cursor.md`
- `composite-index-design.md`
