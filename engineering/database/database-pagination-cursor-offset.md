# Cursor-Based vs Offset Pagination

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

An infinite-scroll feed slows down as users scroll deeper.
Page 1 returns in 8 ms; page 50 returns in 340 ms; page 200
times out. Server logs show full table scans despite an index
on `created_at`. D1 read units spike proportionally with page
depth. Users also intermittently see duplicate posts when a
new post is inserted while they are scrolling.

## Context

SQL `OFFSET` tells the database to read and discard N rows
before returning the next batch. On a 500 k-row posts table,
`LIMIT 20 OFFSET 10000` reads 10 020 rows and returns 20.
SQLite/D1 cannot skip rows inside an index without reading
them first; there is no random-access seek to an offset
position.

Keyset (cursor) pagination uses the last-seen row's values as
a `WHERE` predicate. The index seeks directly to that position
and reads only the 20 rows needed — O(log N + page_size)
instead of O(offset + page_size).

## Why OFFSET Breaks at Scale

```sql
-- Page 1: reads 20 rows — fast
SELECT id, body, created_at
FROM   posts
WHERE  board_id    = ?1
  AND  deleted_at  IS NULL
ORDER  BY created_at DESC, id DESC
LIMIT  20 OFFSET 0;

-- Page 500: reads and discards 9 980 rows — slow
SELECT id, body, created_at
FROM   posts
WHERE  board_id    = ?1
  AND  deleted_at  IS NULL
ORDER  BY created_at DESC, id DESC
LIMIT  20 OFFSET 9980;
```

Rows scanned = `OFFSET + LIMIT`. Every additional page deepens
the scan linearly. At page 500 with `LIMIT 20`, SQLite reads
10 000 rows for every single user request.

Additional problem: if a new post is inserted between page 1
and page 2, `OFFSET 20` skips a row the user should see, or
shows a duplicate. Offset pagination is unstable under
concurrent writes — a critical flaw for a live social feed.

## Keyset Pagination — First Page

```sql
-- Composite partial index covering the cursor columns
CREATE INDEX idx_posts_feed
  ON posts (board_id, created_at DESC, id DESC)
  WHERE deleted_at IS NULL;

-- First page — no cursor needed
SELECT id, body, author_id, created_at
FROM   posts
WHERE  board_id   = ?1
  AND  deleted_at IS NULL
ORDER  BY created_at DESC, id DESC
LIMIT  21; -- fetch 21 to determine has_next_page
```

Fetch `LIMIT + 1` rows. If 21 rows return, pop the last one
and set `has_next_page = true`; return only 20 to the client.

Encode the last visible row's `(created_at, id)` as an opaque
cursor; the client sends it back for the next page. The client
never constructs cursor values itself.

## Keyset Pagination — Subsequent Pages

```sql
-- Next page — cursor = (last_created_at, last_id)
SELECT id, body, author_id, created_at
FROM   posts
WHERE  board_id   = ?1
  AND  deleted_at IS NULL
  AND  (created_at, id) < (?2, ?3)
ORDER  BY created_at DESC, id DESC
LIMIT  21;
```

SQLite supports row-value comparisons (`(a, b) < (x, y)`)
since version 3.15.0. D1 uses a recent SQLite build; confirm
with `SELECT sqlite_version()` before deploying.

Encode the cursor as `btoa(JSON.stringify({c, i}))` on the
server; decode with `JSON.parse(atob(token))` and validate
field types before binding. Always pass decoded values as SQL
parameters (`?2`, `?3`), never interpolate into SQL strings.

## Bi-directional Cursors (Pull-to-Refresh)

For a pull-to-refresh flow that needs both older and newer
posts:

- `next_cursor`: last row's `(created_at, id)` — scroll down.
- `prev_cursor`: first row's `(created_at, id)` — refresh.

```sql
-- Newer posts (pull-to-refresh direction)
SELECT id, body, author_id, created_at
FROM   posts
WHERE  board_id   = ?1
  AND  deleted_at IS NULL
  AND  (created_at, id) > (?2, ?3) -- prev_cursor values
ORDER  BY created_at ASC, id ASC   -- reversed sort order
LIMIT  21;
```

Reverse the result array in application code before returning
to the client so posts are always displayed newest-first
regardless of fetch direction.

## Stable Sort Order Requirement

Cursor pagination requires a fully deterministic sort. If two
rows share the same `created_at`, the tie-breaker `id`
determines which comes first. Without a tie-breaker the cursor
boundary is ambiguous and rows will be duplicated or skipped.

| Sort key                | Stable? | Notes                         |
|-------------------------|---------|-------------------------------|
| `created_at DESC` only  | No      | Ties cause non-determinism    |
| `created_at DESC, id`   | Yes     | id as unique tie-breaker      |
| `id DESC` only          | Yes     | Fine if id encodes time       |
| ULID / UUIDv7 `DESC`    | Yes     | Time-sortable ids work alone  |

## Anti-patterns

- **Exposing raw cursor values to the client** — users can
  manipulate them; always base64-encode the token and validate
  the decoded shape server-side.
- **Mixing OFFSET with cursor pagination** — using both gives
  neither approach's benefits and produces duplicate rows.
- **Skipping the tie-breaker in `ORDER BY`** — causes missing
  or duplicate rows at page boundaries under concurrent writes.
- **Letting the client construct cursors** — the server must
  always generate cursor values from real query results.
- **No index on the cursor columns** — the keyset `WHERE`
  clause degrades to a full table scan without a matching
  composite index.

## Gotchas

- Row-value comparisons `(a, b) < (x, y)` require consistent
  types on both sides; mixing `TEXT` and `INTEGER` in a tuple
  silently degrades to a table scan in some SQLite versions —
  verify with `EXPLAIN QUERY PLAN`.
- ULID and UUIDv7 encode timestamps; using `id DESC` alone as
  the cursor column works only when all IDs use these formats.
- `has_next_page` requires fetching `LIMIT + 1` rows and
  discarding the extra; return only `LIMIT` rows to clients.
- D1's HTTP API has no concept of server-side cursors; the
  keyset approach is the only viable pagination pattern.

## Verification

```bash
# Confirm the keyset query uses the index
wrangler d1 execute <DB> --command "
  EXPLAIN QUERY PLAN
  SELECT id, body, created_at
  FROM   posts
  WHERE  board_id = 'x' AND deleted_at IS NULL
    AND  (created_at, id) < (1700000000000, 'abc')
  ORDER  BY created_at DESC, id DESC LIMIT 20
"
# Expected: SEARCH posts USING INDEX idx_posts_feed
```

## Related

- `database/pagination-offset-vs-cursor.md`
- `database/keyset-pagination.md`
- `database/composite-index-design.md`
- `database/d1-sqlite-query-optimization.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/d1/platform/client-api/
- https://use-the-index-luke.com/no-offset
- https://www.sqlite.org/rowvalue.html
- https://developers.cloudflare.com/d1/best-practices/
