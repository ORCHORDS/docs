# D1 Partial Index Write Performance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A D1 table has a full index on a status column, but the overwhelming majority of rows are in a terminal state (`completed`, `archived`) that is never queried. Every write and compaction touches index pages for rows that will never appear in a `WHERE status = 'pending'` clause, inflating write amplification and slowing hot-path queries.

## Context
D1 is built on SQLite running at Cloudflare's edge. SQLite 3.8.0+ supports partial indexes — indexes with a `WHERE` clause that limits which rows are included. A partial index on `status = 'pending'` stores only the small fraction of rows that are actively queried, making both index reads and index maintenance faster. Because D1 runs in WAL mode, write amplification from a bloated full index directly increases WAL flush size and subsequent read-path checkpoint cost.

## Creating a Partial Index
Only index rows that will actually be queried.

```sql
-- Full index (problematic): indexes ALL rows including completed/archived
CREATE INDEX idx_jobs_status ON jobs(status, created_at);

-- Partial index: only indexes the 'pending' and 'running' minority
CREATE INDEX idx_jobs_active ON jobs(created_at)
  WHERE status IN ('pending', 'running');

-- D1 via Workers binding
await env.DB.prepare(
  `CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(created_at)
   WHERE status IN ('pending', 'running')`
).run();
```

The query planner uses the partial index automatically when the WHERE clause in the query is at least as restrictive as the index predicate.

## Verifying the Planner Uses the Partial Index
Use `EXPLAIN QUERY PLAN` to confirm index selection.

```typescript
// src/db-explain.ts
export async function explainJobQuery(env: Env): Promise<void> {
  const plan = await env.DB.prepare(`
    EXPLAIN QUERY PLAN
    SELECT id, payload FROM jobs
    WHERE status = 'pending'
    ORDER BY created_at ASC
    LIMIT 100
  `).all();

  for (const row of plan.results) {
    console.log(row);
    // Expected: "SEARCH jobs USING INDEX idx_jobs_active (created_at>?)"
    // NOT: "SCAN jobs"
  }
}
```

If the output shows a full table scan, verify the query WHERE clause exactly matches the index predicate; SQLite requires the query filter to imply the index filter.

## Combining Partial Indexes with Covering Indexes
Add frequently projected columns to the index to eliminate table lookups.

```sql
-- Covering partial index: satisfies SELECT id, payload WHERE status='pending'
-- without a secondary lookup into the main table B-tree.
CREATE INDEX idx_jobs_active_covering ON jobs(created_at, id, payload)
  WHERE status IN ('pending', 'running');
```

```typescript
// src/job-queue.ts
export async function pollPendingJobs(
  env: Env,
  limit = 50
): Promise<Job[]> {
  const { results } = await env.DB.prepare(`
    SELECT id, payload
    FROM jobs
    WHERE status = 'pending'
    ORDER BY created_at ASC
    LIMIT ?
  `).bind(limit).all<Job>();

  return results;
}

export async function completeJob(env: Env, id: string): Promise<void> {
  // Updating status OUT of 'pending' removes the row from the partial index,
  // not from the table — write is lighter than a full-index update.
  await env.DB.prepare(`
    UPDATE jobs SET status = 'completed', completed_at = ? WHERE id = ?
  `).bind(Date.now(), id).run();
}
```

## Partial Unique Indexes
Enforce uniqueness only among active rows, allowing multiple completed rows with the same logical key.

```sql
-- Only one active reservation per (user_id, resource_id) at a time.
CREATE UNIQUE INDEX idx_reservations_active_unique
  ON reservations(user_id, resource_id)
  WHERE status = 'active';
```

This replaces an application-level uniqueness check with a constraint the database enforces atomically.

## Anti-patterns
- Creating a partial index whose predicate does not match the query WHERE clause — the planner ignores it and scans the full index or table.
- Indexing high-cardinality terminal states (`completed`) — the index will be large and rarely used; index the small active-state subset instead.
- Using `NOT IN (...)` in the index predicate — SQLite supports this but the planner may not recognise the implication when the query uses `= 'pending'`; test with EXPLAIN.
- Dropping a partial index and replacing it with a full index "for safety" — you lose the write amplification benefit and may double index storage.
- Failing to run `PRAGMA optimize` after bulk status transitions — the query planner statistics may go stale.

## Gotchas
- SQLite's partial index support requires SQLite 3.8.0+; D1 uses a recent SQLite version but verify with `SELECT sqlite_version()`.
- The index predicate must be a deterministic expression; `WHERE created_at > datetime('now', '-1 day')` is NOT a valid partial index predicate (non-deterministic at creation time) — use a fixed status column instead.
- `CREATE INDEX IF NOT EXISTS` is idempotent but silently succeeds even if the existing index has a different definition; drop and recreate if you change the predicate.
- D1 does not expose `ANALYZE` directly; use `PRAGMA optimize` (runs ANALYZE internally) after large data loads.
- Partial indexes are invisible to ORMs that auto-generate full indexes — you must create them via raw SQL migrations.

## Verification
```sql
-- Confirm index exists and its partial predicate
SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'jobs';

-- Measure index page count vs full table
PRAGMA page_count;
PRAGMA freelist_count;

-- Run query planner check
EXPLAIN QUERY PLAN SELECT id FROM jobs WHERE status = 'pending' LIMIT 10;

-- Refresh planner statistics after data changes
PRAGMA optimize;
```

```bash
# Via D1 CLI
wrangler d1 execute MY_DB --command \
  "EXPLAIN QUERY PLAN SELECT id FROM jobs WHERE status='pending' LIMIT 10"
```

## Related
- [`d1-covering-index-multi-column.md`](d1-covering-index-multi-column.md)
- [`d1-query-performance-explain-index.md`](d1-query-performance-explain-index.md)
- [`d1-pragma-optimize-query-planner.md`](d1-pragma-optimize-query-planner.md)
- [`d1-wal-mode-write-throughput.md`](d1-wal-mode-write-throughput.md)
- [`d1-without-rowid-table-read-performance.md`](d1-without-rowid-table-read-performance.md)

## Sources
- https://www.sqlite.org/partialindex.html
- https://developers.cloudflare.com/d1/sql-api/
- https://developers.cloudflare.com/d1/platform/limits/
- https://www.sqlite.org/lang_createindex.html
- https://www.sqlite.org/queryplanner.html
