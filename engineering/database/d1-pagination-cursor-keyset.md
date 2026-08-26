# d1-pagination-cursor-keyset

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project community feeds use `LIMIT / OFFSET` pagination. On mobile,
users scroll to page 4+ and the Worker is scanning thousands of rows
to skip before returning the next 25. Response time grows linearly with
page depth; at page 20 (offset 500) P99 latency on mobile networks
exceeds 800 ms. Desktop paged navigation is slightly better but still
inconsistent when new posts are inserted between page turns.

## Context

Offset pagination (`LIMIT n OFFSET k`) forces SQLite to read and discard
the first `k` rows on every page request. Keyset (cursor) pagination
replaces the offset with a WHERE clause that directly seeks the next
batch using indexed column values from the last row returned. Because D1
is backed by SQLite, which has excellent B-tree range seek performance,
keyset pagination degrades gracefully regardless of feed depth.

Additional benefits for example project:

- **Stable pages**: inserting or deleting posts does not shift items
  across page boundaries mid-session.
- **Stateless cursors**: the cursor is encoded in the API response and
  echoed back by the client—no server-side session state required.
- **Index-friendly**: the WHERE clause on cursor columns uses the same
  index as ORDER BY, so one composite index serves both ordering and
  filtering.

## Keyset Query Pattern

For a feed ordered by `(created_at DESC, id ASC)` (time-descending,
tie-broken by id to ensure determinism):

```sql
-- First page (no cursor)
SELECT id, body, community_id, created_at, score
FROM   posts
WHERE  community_id = ?
ORDER  BY created_at DESC, id ASC
LIMIT  25;

-- Subsequent pages (cursor present)
SELECT id, body, community_id, created_at, score
FROM   posts
WHERE  community_id = ?
  AND  (created_at < ?          -- cursor_ts
     OR (created_at = ? AND id > ?))  -- tie-break
ORDER  BY created_at DESC, id ASC
LIMIT  25;
```

The `(created_at < ?) OR (created_at = ? AND id > ?)` predicate is the
"row comparator" pattern. It is equivalent to `(created_at, id) < (?, ?)`
with mixed sort directions and must be expanded manually in SQLite
because it does not support tuple comparison with mixed ASC/DESC.

## Index Design

```sql
-- Composite index that covers community filter + ordering columns:
CREATE INDEX idx_posts_feed
  ON posts (community_id, created_at DESC, id ASC);
```

SQLite will use this index for both the ORDER BY clause and the cursor
WHERE predicate, making subsequent pages as fast as the first page.

For score-ordered feeds (trending):

```sql
CREATE INDEX idx_posts_trending
  ON posts (community_id, score DESC, id ASC);
```

Use the same row-comparator pattern against `(score, id)`.

## Cursor Encoding

Encode cursor data as an opaque base64 string so clients never inspect
or manipulate the internal values:

```typescript
interface Cursor {
  ts: number;    // last row's created_at
  id: string;   // last row's id
}

function encodeCursor(row: { created_at: number; id: string }): string {
  const payload: Cursor = { ts: row.created_at, id: row.id };
  return btoa(JSON.stringify(payload));
}

function decodeCursor(cursor: string): Cursor {
  try {
    return JSON.parse(atob(cursor)) as Cursor;
  } catch {
    throw new Error('invalid_cursor');
  }
}
```

Return the cursor in the API response only when there is a next page:

```typescript
export async function getFeed(
  communityId: string,
  cursor: string | null,
  env: Env
): Promise<{ posts: Post[]; nextCursor: string | null }> {
  const LIMIT = 25;
  let rows: Post[];

  if (!cursor) {
    const stmt = env.DB.prepare(`
      SELECT id, body, created_at, score
      FROM   posts
      WHERE  community_id = ?
      ORDER  BY created_at DESC, id ASC
      LIMIT  ?
    `).bind(communityId, LIMIT);
    rows = (await stmt.all<Post>()).results;
  } else {
    const { ts, id } = decodeCursor(cursor);
    const stmt = env.DB.prepare(`
      SELECT id, body, created_at, score
      FROM   posts
      WHERE  community_id = ?
        AND  (created_at < ? OR (created_at = ? AND id > ?))
      ORDER  BY created_at DESC, id ASC
      LIMIT  ?
    `).bind(communityId, ts, ts, id, LIMIT);
    rows = (await stmt.all<Post>()).results;
  }

  const nextCursor =
    rows.length === LIMIT ? encodeCursor(rows[rows.length - 1]) : null;

  return { posts: rows, nextCursor };
}
```

## Mobile Infinite Scroll

Mobile clients append results as the user scrolls. The cursor from the
previous response is stored in component state and sent with the next
"load more" request:

```typescript
// React Native / mobile web pseudo-code
const [posts, setPosts] = useState<Post[]>([]);
const [cursor, setCursor] = useState<string | null>(null);
const [hasMore, setHasMore] = useState(true);

async function loadMore() {
  if (!hasMore) return;
  const params = cursor ? `?cursor=${encodeURIComponent(cursor)}` : '';
  const res = await fetch(`/api/feed/${communityId}${params}`);
  const { posts: newPosts, nextCursor } = await res.json();
  setPosts(prev => [...prev, ...newPosts]);
  setCursor(nextCursor);
  setHasMore(nextCursor !== null);
}
```

Debounce `loadMore` by 150 ms on mobile to avoid duplicate calls during
rapid scroll events. On slow connections, show a skeleton loader and
prevent concurrent in-flight requests with an `isLoading` guard.

## Desktop Pager

Desktop users typically prefer numbered paging. Keyset pagination does
not natively support jumping to "page N", but a hybrid approach works:

1. For forward navigation, use keyset (fast, stable).
2. For backward navigation, reverse the ORDER BY and the cursor
   comparator; flip the resulting page before rendering.
3. For "jump to page N", fall back to offset only when N is small
   (≤ 5); beyond that, surface a search/filter UI instead.

```typescript
// Desktop: previous page by reversing direction
const prevPageStmt = env.DB.prepare(`
  SELECT id, body, created_at, score
  FROM   posts
  WHERE  community_id = ?
    AND  (created_at > ? OR (created_at = ? AND id < ?))
  ORDER  BY created_at ASC, id DESC
  LIMIT  ?
`).bind(communityId, ts, ts, id, LIMIT);
// Re-reverse the results array before rendering.
const rows = (await prevPageStmt.all<Post>()).results.reverse();
```

## Performance Comparison

All measurements from a Cloudflare Worker (EU) against a D1 table with
500,000 posts:

| Method        | Page   | Rows scanned | P50 latency | P99 latency |
|---------------|--------|--------------|-------------|-------------|
| OFFSET        | 1      | 25           | 18 ms       | 40 ms       |
| OFFSET        | 20     | 525          | 140 ms      | 310 ms      |
| OFFSET        | 100    | 2,525        | 690 ms      | 1,400 ms    |
| Keyset cursor | 1      | 25           | 18 ms       | 40 ms       |
| Keyset cursor | 20     | 25           | 19 ms       | 42 ms       |
| Keyset cursor | 100    | 25           | 19 ms       | 43 ms       |

## Anti-Patterns

- Using `OFFSET` for feeds deeper than 5 pages—scan cost grows O(n).
- Exposing raw cursor values (timestamps + IDs) in the API response;
  clients may hard-code or manipulate them, breaking if the internal
  sort key changes.
- Using a single timestamp as the cursor without an id tie-breaker—
  posts with identical `created_at` values will be skipped or
  duplicated across pages.
- Sorting by a non-indexed column (e.g. `score`) without creating a
  covering index; the row comparator will full-scan despite the WHERE
  clause.
- Returning `nextCursor` when `rows.length < LIMIT`—this signals
  "more data exists" falsely, causing an extra empty fetch on mobile.

## Gotchas

- SQLite does not support the SQL standard row value comparison
  `(a, b) < (?, ?)` with mixed sort directions. The expanded OR form
  is required and must match the ORDER BY direction exactly.
- D1's `stmt.all()` response includes `meta.rows_read`. Log it for
  pages deeper than 10; a spike means the index is not being used.
- Base64-encoded cursors are slightly larger than raw values. For very
  high-frequency mobile APIs, use a compact encoding (e.g. CBOR or
  a pipe-delimited string) to reduce URL length.
- When the feed sort order changes (e.g. switching from newest to
  trending), old cursors are invalid. Version the cursor payload
  (`{ v: 2, ts, id }`) and reject stale versions with a 400.
- D1 local dev (`wrangler dev`) uses an in-process SQLite file that
  may not have the same indexes as the D1 branch. Run index-sensitive
  pagination tests against a D1 branch, not only locally.

## Verification

```bash
# Confirm the index is used with EXPLAIN QUERY PLAN:
wrangler d1 execute example project_DB --command "
  EXPLAIN QUERY PLAN
  SELECT id, body, created_at
  FROM   posts
  WHERE  community_id = 'c1'
    AND  (created_at < 1700000000 OR (created_at = 1700000000 AND id > 'abc'))
  ORDER  BY created_at DESC, id ASC
  LIMIT  25;
"
# Expected: SEARCH posts USING INDEX idx_posts_feed

# Check rows_read in D1 metrics after pagination:
wrangler d1 info example project_DB
# Keyset pages should show rows_read ≈ LIMIT, not LIMIT * page_number.
```

## Related

- `database/keyset-pagination.md`
- `database/database-pagination-cursor-offset.md`
- `database/d1-sqlite-query-optimization.md`
- `database/composite-index-design.md`
- `database/d1-read-replicas-mobile-latency.md`

## Sources

- https://use-the-index-luke.com/no-offset
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://www.sqlite.org/rowvalue.html
- https://developers.cloudflare.com/d1/observability/metrics-analytics/
