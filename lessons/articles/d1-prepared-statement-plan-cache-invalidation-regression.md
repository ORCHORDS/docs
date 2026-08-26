# D1 Prepared Statement Plan Cache Invalidation Regression Lesson

Date: 2026-08-23 / Author: example.com / Status: production

---

## Incident Summary

On 2026-06-02 a schema migration added a composite index to a high-traffic D1 table.
Within 10 minutes of the migration completing, the application began returning stale
query plans that bypassed the new index entirely. Full-table scans caused CPU time
per request to spike 8x, exhausting the D1 row budget on the affected database within
90 minutes of the migration. The issue was invisible in staging because staging did
not exercise the same prepared-statement lifecycle that production Workers use.

---

## Context

- Database: `catalog-prod` (~4.2 million rows in `tracks` table)
- Cloudflare Workers runtime: `workers-rs` Rust bindings + D1 HTTP binding
- Deployment strategy: rolling deploy via `wrangler deploy` with zero downtime
- Affected query: `SELECT … FROM tracks WHERE artist_id = ? AND genre_id = ?`
- Migration added: `CREATE INDEX idx_tracks_artist_genre ON tracks(artist_id, genre_id)`
- D1 row read budget at incident peak: 98% consumed at 14:30 UTC (limit: 25M/day)

---

## Timeline

**13:45 UTC** — Schema migration runs via `wrangler d1 execute`. Index creation
completes in 47 seconds. Migration script exits 0.

**13:47 UTC** — `wrangler deploy` rolls out new Worker binaries that contain no code
change. Deploy completes.

**13:52 UTC** — P99 CPU time per request rises from 4 ms to 34 ms on the catalog
search endpoint. No alert fires (threshold: 100 ms).

**14:18 UTC** — D1 row read counter alert fires at 75% of daily budget consumed.
On-call engineer assumes a traffic spike and checks request counts — they are within
normal range.

**14:24 UTC** — Engineer enables D1 query explain logging for the catalog search
Worker. First `EXPLAIN QUERY PLAN` results show `SCAN tracks` instead of
`SEARCH tracks USING INDEX idx_tracks_artist_genre`.

**14:31 UTC** — Engineer identifies the old prepared statement plan is being reused.
Issues a forced Worker redeploy (`--force` flag) to flush in-memory prepared
statement caches across all isolates.

**14:34 UTC** — New plans picked up: `SEARCH tracks USING INDEX`. CPU time per
request drops to 3 ms. Row reads normalise.

---

## Root Cause

SQLite's prepared statement cache binds the query plan at prepare time, not at
execution time. When the D1 Workers binding prepares a statement, it resolves the
query plan against the schema snapshot visible at that moment and caches the compiled
bytecode. Adding an index does not invalidate existing prepared statements in-flight
inside running Worker isolates because:

1. The D1 HTTP binding caches prepared statement handles per-isolate.
2. Isolates are long-lived (can serve requests for tens of minutes between cold-starts).
3. The DDL migration runs on the D1 server side; there is no push-based cache
   invalidation signal sent to connected Worker isolates.

The result: Worker isolates created before the migration continued executing the old
plan (full-table scan). Only new isolates, or isolates that re-prepared the statement
after their internal TTL expired, picked up the new index-using plan.

---

## Why Staging Missed It

Staging uses a separate database but exercises the same Worker code. The critical
difference: staging runs a single low-concurrency isolate that is cold-started fresh
on each test run. A cold-start always re-prepares statements, so staging always saw
the post-migration plan. Production has a pool of warm isolates that never recycled
during the test window.

---

## Fix (Immediate)

```bash
# Force a no-op redeploy to evict all warm isolates.
wrangler deploy --force
```

A `--force` redeploy increments the Worker's content hash even if source bytes are
unchanged, causing the runtime to retire all existing isolates and spin up fresh ones.
Fresh isolates re-prepare all statements against the current schema.

---

## Fix (Structural)

### 1. Always redeploy the Worker as part of every schema migration

Add a post-migration step in the migration runbook:

```bash
wrangler d1 execute catalog-prod --file=./migrations/0042_add_artist_genre_index.sql
wrangler deploy --force   # evict stale prepared statement caches
```

The deploy costs ~10 seconds of isolate warm-up latency but guarantees plan freshness.

### 2. Add post-migration query plan verification

```sql
-- Run immediately after migration, before rolling out Worker:
EXPLAIN QUERY PLAN
  SELECT track_id, title FROM tracks WHERE artist_id = 1 AND genre_id = 5;
-- Expected output must contain: SEARCH tracks USING INDEX idx_tracks_artist_genre
```

Gate the migration pipeline on this assertion; fail the CI step if a full scan appears.

### 3. Include schema version in prepared statement cache keys

If the application manually manages statement handles, invalidate the cache when the
D1 schema `pragma user_version` changes:

```ts
const { user_version } = await db.prepare('PRAGMA user_version').first();
if (user_version !== cachedSchemaVersion) {
  preparedStatementCache.clear();
  cachedSchemaVersion = user_version;
}
```

D1's built-in binding does not expose this today, but it is a pattern available for
custom HTTP-layer D1 clients.

---

## Prevention

- **Treat schema migrations and Worker deploys as an atomic pair.** They are not
  independent operations when prepared statement plans are cached in isolate memory.
- **Run `EXPLAIN QUERY PLAN` assertions in integration tests** for every query that
  touches indexed columns. Include them in the post-migration validation step.
- **Monitor row reads per request as a latency proxy.** A sudden increase in rows
  read per request with stable request volume is a strong signal of a plan regression.
- **Set D1 row read budget alerts at 50% and 70%**, not only at 90%. Budget
  exhaustion is a lagging indicator; earlier thresholds give remediation time.

---

## Anti-patterns

- **Running DDL migrations without a subsequent Worker redeploy:** Schema changes
  are invisible to warm isolates until they cold-start.
- **Assuming SQLite auto-analyses new indexes into existing cached plans:** SQLite
  does not retroactively update compiled statement bytecode.
- **Staging environments that always cold-start:** They cannot reproduce warm-isolate
  plan-cache bugs, which are a class of production-only failures.
- **Treating D1 row budget alerts as traffic alarms:** Row-read spikes with flat
  request counts almost always indicate a plan regression, not a traffic anomaly.

---

## Gotchas

- D1 does not surface prepared statement plan age or cache hit/miss metrics. You
  cannot observe stale plans without running `EXPLAIN QUERY PLAN` explicitly.
- `wrangler d1 execute` runs DDL synchronously and exits, but the Worker runtime
  has no awareness that DDL was just executed. Plan invalidation is solely the
  operator's responsibility.
- D1 `ANALYZE` (which updates query statistics) does not run automatically after
  index creation. If the new index has skewed cardinality, the planner may still
  prefer a full scan even with a fresh isolate. Run `ANALYZE tracks` after large
  index builds.
- In `wrangler dev` the isolate restarts on every file save, masking this class
  of bug entirely during local development.

---

## Verification

1. After the post-migration `--force` deploy, run `EXPLAIN QUERY PLAN` against the
   live database and confirm index usage.
2. Check P99 CPU time per request on the catalog search endpoint drops to ≤ 5 ms
   within 2 minutes of the redeploy.
3. Check D1 row reads per request in Analytics Engine: should match pre-migration
   baseline (≤ 5 rows per `tracks` query).
4. Confirm the migration runbook checklist in the ops wiki now includes a mandatory
   `wrangler deploy --force` step with sign-off.

---

## Related

- `d1-schema-migration-table-lock-peak-traffic-postmortem.md`
- `d1-migration-rollback-failed-production-lesson.md`
- `d1-replica-stale-read-production-incident.md`
- `d1-foreign-key-constraint-migration-production-outage.md`
- `index-before-not-after-performance-problem.md`

---

## Sources

- SQLite Prepared Statement documentation: https://www.sqlite.org/c3ref/prepare.html
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- SQLite EXPLAIN QUERY PLAN: https://www.sqlite.org/eqp.html
- Internal incident ticket INC-2026-089 (restricted)
