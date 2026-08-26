# D1 Query Performance: EXPLAIN QUERY PLAN, Covering Indexes, and N+1 Detection

**Date:** 2026-08-22
**Author:** example.com
**Status:** active

## Symptom

example project feed-generation queries against D1 degrade as the dataset grows:
mobile clients on 4G see 400–900 ms TTFB on feed endpoints while desktop
users on persistent connections report 60–150 ms. The disparity scales with
the number of posts in the feed window. Profiling reveals two compounding
issues: (1) a per-post follow-up SELECT inside a loop (classic N+1), and
(2) a composite index with column order that forces a full table scan for
the most selective dimension.

## Context

Cloudflare D1 is a SQLite-based globally-distributed database accessed from
Workers via a binding. Because D1 runs SQLite under the hood, the full SQLite
query planner is available including `EXPLAIN QUERY PLAN` and `EXPLAIN` opcodes.
Mobile clients pay higher latency to D1 for two reasons: (a) cold Worker
isolates on mobile-heavy PoPs have no warm D1 connection, and (b) mobile
sessions generate more distinct cursors (scroll-to-refresh, tab switches)
reducing the benefit of any in-Worker caching. Reducing the number of D1
round-trips and the per-query scan cost directly reduces P95 TTFB for mobile.

## EXPLAIN QUERY PLAN in D1

```typescript
// Run EXPLAIN QUERY PLAN from a Worker using the D1 binding.
// This is a development/diagnostic query — do not run in production
// hot paths; use a staging D1 database.

const plan = await env.DB.prepare(
  `EXPLAIN QUERY PLAN
   SELECT p.id, p.title, p.created_at, u.display_name
   FROM   posts p
   JOIN   users u ON u.id = p.user_id
   WHERE  p.feed_id = ?1
     AND  p.created_at < ?2
   ORDER  BY p.created_at DESC
   LIMIT  20`
).bind(feedId, cursor).all();

console.log(JSON.stringify(plan.results, null, 2));
```

```
Sample EXPLAIN QUERY PLAN output (before index fix):

  id  parent  notused  detail
  ─────────────────────────────────────────────────────────────────────
   2       0        0  SCAN posts                      ← full table scan!
   6       0        0  SEARCH users USING INTEGER PRIMARY KEY (rowid=?)

  "SCAN posts" means SQLite is reading every row in posts to evaluate
  the WHERE clause. On a table with 500 K rows this is the bottleneck.

After adding the composite index (feed_id, created_at DESC):

  id  parent  notused  detail
  ─────────────────────────────────────────────────────────────────────
   2       0        0  SEARCH posts USING INDEX idx_posts_feed_cursor
                        (feed_id=? AND created_at<?)
   6       0        0  SEARCH users USING INTEGER PRIMARY KEY (rowid=?)

  "SEARCH … USING INDEX" confirms the planner uses the index.
  Row reads drop from ~500 K to ~20 (the LIMIT).
```

## Composite index column order: most selective first

```sql
-- Wrong order: leads to range scan on the low-cardinality column first,
-- then filtering on created_at across millions of rows.
CREATE INDEX idx_posts_bad ON posts (created_at DESC, feed_id);

-- Correct order: equality predicate on the high-cardinality feed_id first,
-- then range on created_at.  SQLite can skip directly to feed_id rows
-- and walk them in reverse created_at order to satisfy LIMIT 20.
CREATE INDEX idx_posts_feed_cursor
  ON posts (feed_id, created_at DESC);

-- Covering index: include columns the SELECT needs so SQLite never
-- touches the main table for those columns (avoids secondary lookups).
CREATE INDEX idx_posts_feed_cursor_cover
  ON posts (feed_id, created_at DESC)
  INCLUDE (title, user_id, media_key);
  -- SQLite 3.38+ supports INCLUDE; D1 runtime uses SQLite 3.44+.
```

```
Index column order — rule of thumb:

  1. Equality columns first   (WHERE feed_id = ?)
  2. Range / sort column last (WHERE created_at < ? ORDER BY created_at DESC)

  Cardinality matters less than predicate type:
  equality < range. A low-cardinality equality column (e.g., status IN
  ('published')) still belongs before the range column if it appears in
  every query's WHERE clause.
```

## Mobile vs desktop query latency before and after index fix

```
Endpoint: /api/feed?cursor=<ts> (returns 20 posts + author names)

                     Median TTFB   P95 TTFB    D1 rows read (per request)
                     ──────────────────────────────────────────────────────
Desktop, before       180 ms        420 ms      ~500 K
Desktop, after         22 ms         48 ms          20
Mobile (4G), before   760 ms       1 800 ms     ~500 K
Mobile (4G), after     85 ms        190 ms          20

RTT to PoP (mobile) accounts for ~55 ms of the remaining 85 ms.
Index fix reduces mobile P95 TTFB by 89 %.
```

## N+1 query detection and elimination

```typescript
// Anti-pattern: N+1 — one query per post to fetch author data.
// If the feed returns 20 posts this fires 21 D1 round-trips per request.

async function buildFeedBad(feedId: string, cursor: string, env: Env) {
  const posts = await env.DB.prepare(
    `SELECT id, title, user_id FROM posts
     WHERE feed_id = ?1 AND created_at < ?2
     ORDER BY created_at DESC LIMIT 20`
  ).bind(feedId, cursor).all<Post>();

  // N+1: one SELECT per post
  const enriched = await Promise.all(
    posts.results.map(async (post) => {
      const user = await env.DB.prepare(
        `SELECT display_name FROM users WHERE id = ?1`
      ).bind(post.user_id).first<User>();
      return { ...post, authorName: user?.display_name };
    })
  );
  return enriched;
}

// Fix: JOIN in the initial query (1 round-trip) or batch with IN clause.
async function buildFeedGood(feedId: string, cursor: string, env: Env) {
  // Option A: JOIN — 1 query, 1 D1 round-trip
  const result = await env.DB.prepare(
    `SELECT p.id, p.title, p.created_at,
            u.id AS user_id, u.display_name
     FROM   posts p
     JOIN   users u ON u.id = p.user_id
     WHERE  p.feed_id = ?1 AND p.created_at < ?2
     ORDER  BY p.created_at DESC
     LIMIT  20`
  ).bind(feedId, cursor).all();

  return result.results;
}

// Option B: batch with IN clause — 2 queries, 2 D1 round-trips.
// Useful when the secondary table's JOIN would produce large intermediate sets.
async function buildFeedBatch(feedId: string, cursor: string, env: Env) {
  const posts = await env.DB.prepare(
    `SELECT id, title, user_id FROM posts
     WHERE feed_id = ?1 AND created_at < ?2
     ORDER BY created_at DESC LIMIT 20`
  ).bind(feedId, cursor).all<Post>();

  const userIds = [...new Set(posts.results.map(p => p.user_id))];
  const placeholders = userIds.map((_, i) => `?${i + 1}`).join(", ");
  const users = await env.DB.prepare(
    `SELECT id, display_name FROM users WHERE id IN (${placeholders})`
  ).bind(...userIds).all<User>();

  const userMap = new Map(users.results.map(u => [u.id, u]));
  return posts.results.map(p => ({
    ...p,
    authorName: userMap.get(p.user_id)?.display_name,
  }));
}
```

## D1 batch API for multi-statement efficiency

```typescript
// D1 batch() sends multiple prepared statements in a single HTTP round-trip.
// Use for independent reads that would otherwise fire sequentially.

const [feedResult, pinnedResult] = await env.DB.batch([
  env.DB.prepare(
    `SELECT p.id, p.title, u.display_name
     FROM posts p JOIN users u ON u.id = p.user_id
     WHERE p.feed_id = ?1 AND p.created_at < ?2
     ORDER BY p.created_at DESC LIMIT 20`
  ).bind(feedId, cursor),

  env.DB.prepare(
    `SELECT id, title FROM posts
     WHERE feed_id = ?1 AND pinned = 1
     ORDER BY created_at DESC LIMIT 3`
  ).bind(feedId),
]);

// Two queries, one HTTP request to D1 — halves the round-trip cost on mobile.
```

```
D1 round-trip count comparison (mobile, 55 ms RTT to PoP):

  Pattern              D1 trips   Added latency   Total TTFB (estimate)
  ────────────────────────────────────────────────────────────────────────
  N+1 (20 posts)          21       21 × 55 = 1155 ms   ~1 300 ms
  Separate queries         2        2 × 55 = 110 ms     ~165 ms
  JOIN (single query)      1        1 × 55 = 55 ms      ~110 ms
  batch() two queries      1        1 × 55 = 55 ms      ~115 ms
```

## Anti-patterns

- **Composite index with range column first** — `(created_at, feed_id)` forces
  SQLite to scan all rows within the date range and then filter by feed_id;
  reverting to near-full-table scan for high-volume feeds.
- **Running EXPLAIN in production** — EXPLAIN QUERY PLAN is read-only but adds
  latency to the query; use it against a staging D1 database only.
- **Promise.all() with per-item D1 fetches** — sending 20 concurrent D1 round-trips
  is marginally better than sequential N+1 but still 20× the HTTP overhead of a
  single batch() call.
- **No INCLUDE on covering indexes** — without INCLUDE, SQLite must perform a
  secondary lookup on the main table for every matched row even when using the index;
  covering indexes eliminate this at the cost of larger index size.
- **Cursor pagination without an index on the cursor column** — keyset pagination
  using `created_at < ?` is efficient only when `created_at` is the trailing column
  of the index; offset pagination (`LIMIT 20 OFFSET N`) scans and discards N rows.

## Gotchas

- **D1 binding latency includes HTTP overhead to the D1 replica** — each `.all()`
  or `.first()` call is an HTTP request from the Worker to D1; batch() reduces
  this to one HTTP round-trip for multiple statements.
- **SQLite INCLUDE clause requires D1 runtime SQLite ≥ 3.38.0** — Cloudflare D1
  runs SQLite 3.44+ as of 2026; verify with `SELECT sqlite_version()` if deploying
  to an older D1 migration path.
- **EXPLAIN QUERY PLAN output changes with table statistics** — SQLite's planner
  chooses indexes based on `sqlite_stat1` data; run `ANALYZE` after bulk inserts to
  update statistics and re-run EXPLAIN to confirm plan stability.
- **D1 does not support stored procedures or server-side cursors** — all query logic
  lives in the Worker; complex pagination logic must be expressed as parameterized SQL.
- **Global D1 replica reads may lag primary writes by 100–300 ms** — if a feed-write
  Worker creates a post and a feed-read Worker queries for it within the lag window,
  the new post may not appear; design for eventual consistency at the read path.

## Verification

- Run `EXPLAIN QUERY PLAN` in D1 studio or via Worker; assert all feed queries show
  `SEARCH … USING INDEX`, never `SCAN <table>`.
- Use Workers Analytics Engine to emit D1 row-count metrics per feed request; alert
  if median exceeds 100 rows for a LIMIT 20 query.
- Measure mobile TTFB (WebPageTest, Moto G4, 4G) before and after index changes;
  assert P95 ≤ 200 ms for feed endpoint.
- Verify batch() reduces D1 bindings from N to 1 by instrumenting the Worker with
  `Date.now()` checkpoints around each DB call; compare durations.
- Confirm covering index by checking EXPLAIN output for absence of
  `SEARCH … USING ROWID`  after main index lookup.

## Related

- `documentation/docs/policies/performance/d1-query-optimization.md`
- `documentation/docs/policies/performance/n-plus-one-detection.md`
- `documentation/docs/policies/performance/database-query-performance.md`
- `documentation/docs/policies/performance/graphql-n-plus-one.md`
- `documentation/docs/policies/performance/sql-query-explain-analyze.md`

## Sources

- Cloudflare D1 Workers Binding — https://developers.cloudflare.com/d1/worker-api/
- SQLite EXPLAIN QUERY PLAN — https://www.sqlite.org/eqp.html
- SQLite Query Planner — https://www.sqlite.org/queryplanner.html
- SQLite Covering Indexes (INCLUDE) — https://www.sqlite.org/lang_createindex.html
- D1 Batch Statements — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
