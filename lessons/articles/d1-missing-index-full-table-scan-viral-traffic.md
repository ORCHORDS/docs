# D1 Missing Index — Full Table Scan Under Viral Traffic

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1-backed API endpoint serving a creator's post feed degraded from sub-5ms responses to 8-second timeouts during a viral traffic event. The endpoint had performed acceptably during development and early growth, but an untested code path — sorting posts by `created_at` within a filtered `author_id` set — had no supporting index. At 10K rows the full table scan was imperceptible. At 2 million rows it was catastrophic.

---

## Context

The platform allows creators to publish posts. A feed endpoint returns the 20 most recent posts by a given author:

```sql
SELECT id, title, body, created_at
FROM posts
WHERE author_id = ?
ORDER BY created_at DESC
LIMIT 20;
```

The `posts` table had a primary key on `id` and a single index on `author_id` created early in development. That index was dropped in a schema migration 4 months prior when the team consolidated indexes "to save space" — the drop was not reviewed against query patterns. No `EXPLAIN QUERY PLAN` check was part of the PR process.

**Stack:**
- Cloudflare D1 (SQLite-compatible)
- Cloudflare Workers (API layer)
- Analytics Engine (observability sink via Tail Workers)
- Table size at incident: ~2.1 million rows

---

## Incident Timeline

### Background — Table Growth

| Date | Row Count | Query Duration (p50) |
|---|---|---|
| 2026-02-01 | 10,000 | 2ms |
| 2026-04-15 | 150,000 | 18ms |
| 2026-07-01 | 900,000 | 890ms |
| 2026-08-20 | 2,100,000 | 8,200ms |

The slow degradation between February and July was masked by the fact that the affected creator accounts were not heavily trafficked. p50 across all requests remained low because most requests hit popular creators with few posts or used different query patterns.

### Incident Day — 2026-08-20

- `11:14 UTC` — A high-profile creator publishes content that goes viral. Traffic to their feed endpoint increases 40x within 20 minutes.
- `11:22 UTC` — Worker error rate spikes to 34% (D1 query timeout errors). On-call notified via PagerDuty.
- `11:31 UTC` — Investigation begins. `wrangler tail` shows `Error: D1_ERROR: interrupted` on the feed endpoint.
- `11:45 UTC` — Analytics Engine query confirms D1 query duration p95 on `/feed` endpoint: `8,340ms`.
- `11:52 UTC` — `EXPLAIN QUERY PLAN` run against the query in D1 console:

```
QUERY PLAN
`--SCAN posts (~2100000 rows estimated)
```

Full table scan confirmed — no index used.

- `12:08 UTC` — `CREATE INDEX` issued online (see fix below).
- `12:10 UTC` — Index creation completes (approximately 90 seconds on 2.1M rows).
- `12:11 UTC` — Error rate returns to 0%. Feed endpoint p95 drops to 3ms.

---

## Root Cause

The query filters on `author_id` and sorts on `created_at`. For SQLite (and D1) to satisfy both the filter and the sort without scanning the full table, a **composite index** on `(author_id, created_at)` is required. A single-column index on `author_id` alone cannot satisfy the `ORDER BY created_at DESC` without a secondary sort step over all rows matching `author_id`.

With 2.1M rows and no composite index, every request to `/feed?author=<id>` caused D1 to:
1. Scan all 2.1M rows to find matching `author_id` values.
2. Sort all matching rows by `created_at`.
3. Return the top 20.

At 40x normal traffic concurrency, D1 hit its query time limit and began returning `interrupted` errors.

---

## Fix — Online Index Creation

```sql
-- Run directly in D1 console or via Workers migration
CREATE INDEX IF NOT EXISTS idx_posts_author_created
  ON posts (author_id, created_at DESC);
```

After index creation, `EXPLAIN QUERY PLAN` confirms:

```
QUERY PLAN
`--SEARCH posts USING INDEX idx_posts_author_created (author_id=?)
```

D1 (SQLite) can now seek directly to the `author_id` partition within the index, which is already sorted by `created_at DESC`, satisfying both the `WHERE` and `ORDER BY` with a single index scan and a `LIMIT 20` early exit.

**No downtime was required.** D1's SQLite engine supports concurrent reads during index creation. The 90-second index build was transparent to live traffic (in-flight queries finished against the unindexed table; new queries after creation used the index immediately).

---

## Query Plan Verification

Always verify with `EXPLAIN QUERY PLAN` before and after index changes:

```sql
-- Before: full scan
EXPLAIN QUERY PLAN
SELECT id, title, body, created_at
FROM posts
WHERE author_id = 'usr_abc123'
ORDER BY created_at DESC
LIMIT 20;
-- Output: SCAN posts (~2100000 rows estimated)

-- After: index seek
-- Output: SEARCH posts USING INDEX idx_posts_author_created (author_id=?)
```

---

## Anti-patterns / What Went Wrong

1. **Dropping an index without querying all dependent query patterns.** The original `author_id` index was dropped as a cleanup measure. No one ran `EXPLAIN QUERY PLAN` against the active queries to verify the impact.

2. **Testing only at development-scale row counts.** 10K rows hid the problem completely. A staging environment with production-scale data (or at minimum 500K+ rows) would have revealed the 2ms → 8s curve.

3. **No `EXPLAIN QUERY PLAN` gate in PR review.** D1 query changes were reviewed for correctness but not for execution plan. A one-line plan check would have caught the missing index immediately.

4. **Composite index requirement not understood by team.** Several engineers assumed a single-column index on `author_id` was sufficient for a query that also sorted by `created_at`. This is a SQLite (and D1) fundamental: the index must cover both the filter column and the sort column to avoid a full scan.

5. **Monitoring did not distinguish endpoint-level D1 duration.** The Analytics Engine sink captured D1 duration globally. Per-endpoint D1 duration was not tracked, so the slow feed endpoint was averaged out by fast requests on other routes.

---

## Gotchas

- **D1 is SQLite — SQLite index rules apply exactly.** If you know SQLite query planning, you know D1 query planning. Composite index column order matters: `(author_id, created_at)` serves `WHERE author_id = ? ORDER BY created_at` but `(created_at, author_id)` does not.
- **`LIMIT` does not help without a supporting index on the sort column.** D1 must find and sort all candidate rows before it can apply `LIMIT`.
- **Online `CREATE INDEX` in D1 is safe but not instantaneous.** On large tables expect 1–3 minutes. During creation, reads continue normally; new writes are temporarily serialized.
- **`SELECT *` in production queries is a warning sign.** It was not the cause here, but returning all columns increases the data transferred and makes it harder to reason about index coverage.
- **Analytics Engine D1 metrics are per-Worker, not per-query.** To get per-query duration, emit a custom `duration_ms` data point from within the Worker for each D1 call.

---

## Process Change Adopted

### Mandatory `EXPLAIN QUERY PLAN` in PR Review

Added to the repository's pull request template:

```markdown
## D1 Query Checklist (required for any PR touching D1 queries)
- [ ] `EXPLAIN QUERY PLAN` output included for all new or modified queries
- [ ] No `SCAN <table>` in query plan (must be `SEARCH ... USING INDEX`)
- [ ] Composite index covers both filter and sort columns
- [ ] Tested against a dataset of >= 100K rows in staging D1
```

### Per-Endpoint D1 Duration Metric

```typescript
// workers/api/feed.ts
const t0 = Date.now();
const posts = await env.DB.prepare(
  'SELECT id, title, body, created_at FROM posts WHERE author_id = ? ORDER BY created_at DESC LIMIT 20'
).bind(authorId).all();
const d1Ms = Date.now() - t0;

// Emit to Analytics Engine
env.AE.writeDataPoint({
  indexes: ['feed'],
  doubles: [d1Ms],
  blobs: [authorId],
});
```

---

## Verification

- Post-incident p95 D1 duration on `/feed` endpoint: 3ms (down from 8,340ms).
- `EXPLAIN QUERY PLAN` confirms index seek on all affected queries.
- Staging D1 instance seeded with 3M rows shows consistent sub-5ms p95.
- PR template `EXPLAIN QUERY PLAN` checklist enforced in all subsequent D1 migrations.

---

## Related

- `kv-eventual-consistency-cache-poisoning-incident.md`
- `durable-objects-alarm-delivery-guarantee-lesson.md`
- D1 documentation: [Query performance](https://developers.cloudflare.com/d1/learning/query-performance/)
- SQLite documentation: [Query Planner](https://www.sqlite.org/queryplanner.html)

---

## Sources

- Internal incident report `INC-2026-0820`
- D1 Analytics Engine query output captured during investigation
- `EXPLAIN QUERY PLAN` outputs before and after fix
- PR review checklist: `docs/pr-template.md`
