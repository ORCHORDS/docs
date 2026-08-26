# D1 / SQLite Query Optimization

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Workers requests take 200–800 ms when they should complete in
under 30 ms. The Cloudflare dashboard shows D1 read units
spiking unexpectedly for feeds with only a few hundred active
users. CPU time is dominated by query wait, not JS execution.

## Context

Cloudflare D1 is a serverless SQLite implementation served
over HTTP. Each Worker instance holds no persistent connection;
every query goes through D1's HTTP API. This means:

- Round-trip latency matters — every sequential query adds up.
- SQLite's query planner uses a subset of Postgres-style hints.
- `EXPLAIN QUERY PLAN` reveals scan type (FULL TABLE SCAN vs
  INDEX SCAN) but not row estimates or cost numbers.
- The D1 free tier counts read units per row read, so a full
  table scan on a 50 k-row posts table is expensive.

## Reading EXPLAIN QUERY PLAN

Run `EXPLAIN QUERY PLAN` before any slow query to verify the
planner chose an index.

```sql
EXPLAIN QUERY PLAN
SELECT p.id, p.body, p.created_at
FROM   posts p
WHERE  p.author_id  = ?1
  AND  p.deleted_at IS NULL
ORDER  BY p.created_at DESC
LIMIT  20;
```

Good output — index used:
```
SEARCH posts AS p USING INDEX
  idx_posts_author_created (author_id=? created_at<?)
```

Bad output — full table scan:
```
SCAN posts AS p
```

If you see `SCAN`, add or fix the index. Run via Wrangler:

```bash
wrangler d1 execute <DB> --command \
  "EXPLAIN QUERY PLAN SELECT ..."
```

## Index Selection and Covering Indexes

For a social feed ordered by recency, a covering index keeps
SQLite inside the index B-tree without touching table rows.

```sql
-- Covering index: all columns the query needs are in the
-- index, so SQLite never reads the table heap.
CREATE INDEX idx_posts_author_feed
  ON posts (author_id, created_at DESC, id, body)
  WHERE deleted_at IS NULL;
```

Column order in a composite index matters:

| Query filter              | Index that helps                  |
|---------------------------|-----------------------------------|
| `author_id = ?`           | `(author_id, created_at)`         |
| `created_at > ?`          | `(created_at)`                    |
| `author_id = ?` + body    | covering idx with body column     |
| `board_id = ?` feed       | `(board_id, created_at DESC, id)` |

Put high-cardinality columns first. A low-cardinality column
(e.g., a 3-value status) should trail the equality filters.

## Partial Indexes for Soft-Delete Workloads

Every query in an anonymous social app filters soft-deleted
rows. Without a partial index the planner reads every row and
filters in memory, inflating read units proportionally.

```sql
-- Without partial index: scans all posts including deleted
CREATE INDEX idx_posts_feed
  ON posts (board_id, created_at DESC);

-- With partial index: index covers only live rows
CREATE INDEX idx_posts_feed_live
  ON posts (board_id, created_at DESC)
  WHERE deleted_at IS NULL;
```

The `WHERE` clause in the index definition must exactly match
the `WHERE` clause in the query for SQLite to use it. A
parameterized value in the index `WHERE` is not supported.

## Batch Queries — Avoiding N+1 in Workers

Workers have no ORM eager-loading. N+1 patterns emerge when a
feed loads 20 posts and then fires one query per post to fetch
author metadata.

```ts
// Good — 2 round-trips instead of 21 using D1 batch()
const [postsRes, usersRes] = await db.batch([
  db.prepare(`
    SELECT p.id, p.body, p.author_id, p.created_at
    FROM   posts p
    WHERE  p.board_id   = ?1
      AND  p.deleted_at IS NULL
    ORDER  BY p.created_at DESC, p.id DESC
    LIMIT  20
  `).bind(boardId),
  db.prepare(`
    SELECT id, handle, avatar_url
    FROM   users
    WHERE  id IN (
      SELECT DISTINCT author_id
      FROM   posts
      WHERE  board_id   = ?1
        AND  deleted_at IS NULL
      ORDER  BY created_at DESC LIMIT 20
    )
  `).bind(boardId),
]);
```

`db.batch()` sends all statements in a single HTTP request
and returns results in the same order. Wrap writes in a
transaction by prepending a `db.prepare('BEGIN')` statement.

## Anti-patterns

- **`SELECT *`** — pulls unused columns over HTTP; always name
  columns explicitly in production queries.
- **No index on foreign keys** — SQLite does not auto-index
  FKs; every JOIN on an un-indexed FK is a full table scan.
- **OFFSET-based pagination** — `OFFSET 1000` makes SQLite
  read and discard 1 000 rows; use keyset pagination.
- **Sequential `await` in a loop** — each `await db.prepare()`
  is a network round-trip; batch or JOIN instead.
- **`json_extract()` in WHERE** — SQLite cannot use a B-tree
  index on a function call; extract to real columns.

## Gotchas

- `EXPLAIN QUERY PLAN` output in D1 is returned as result
  rows, not printed; parse `results[0].detail` in JS.
- The partial index `WHERE` must be a static expression;
  parameterized predicates in the index are not supported.
- SQLite can use an index for both `ASC` and `DESC` scans, but
  including `DESC` in the index definition helps the planner
  confirm sort direction, avoiding a separate sort step.
- `db.batch()` is not an ACID transaction unless you include
  `BEGIN` / `COMMIT` statements in the batch array.
- Worker CPU time counts during JS object mapping, not while
  waiting for D1; slow serialization can hide a fast query.

## Verification

```bash
# Check for SCAN (bad) vs SEARCH (good)
wrangler d1 execute <DB> --command \
  "EXPLAIN QUERY PLAN
   SELECT id, body FROM posts
   WHERE board_id = 'x' AND deleted_at IS NULL
   ORDER BY created_at DESC LIMIT 20" \
  | grep -E "SCAN|SEARCH"

# Count read units in Cloudflare dashboard:
# Workers & Pages → your Worker → Metrics → D1 Read Units
```

## Related

- `database/sqlite-d1-patterns.md`
- `database/partial-indexes.md`
- `database/n-plus-one-query-detection.md`
- `database/covering-indexes.md`
- `database/database-pagination-cursor-offset.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/d1/best-practices/
- https://www.sqlite.org/eqp.html
- https://www.sqlite.org/partialindex.html
- https://developers.cloudflare.com/d1/observability/metrics-analytics/
