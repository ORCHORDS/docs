# D1 JSON Virtual Generated Column Index

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 table stores semi-structured data in a JSON text column (e.g., `metadata TEXT`
containing `{"userId":"…","tier":"pro","region":"eu-west"}`). Queries that filter on a
nested JSON field (`WHERE json_extract(metadata, '$.tier') = 'pro'`) perform full table
scans even when an index exists on `metadata` itself, because the index covers the raw JSON
string, not the extracted value. Response times scale linearly with row count rather than
remaining constant.

---

## Context

SQLite (which underlies D1) supports **generated columns** — virtual or stored columns
whose value is computed from an expression over other columns in the same row. When you
define a generated column based on `json_extract()`, SQLite can build a real B-tree index
on the extracted value. D1 exposes the same SQLite 3.37+ feature.

Two flavours:
- **VIRTUAL** — value computed on read, not persisted. Zero storage cost; adds CPU at
  query time. Suitable for indexed columns (the index stores the value).
- **STORED** — value persisted on every write. Higher write amplification; allows the
  column to appear in covering indexes alongside other stored columns without recomputing.

For pure index purposes, VIRTUAL is usually preferable: the index stores the extracted
value, so reads hit only the index without touching the base column.

This technique is distinct from `d1-covering-index-multi-column.md`, which covers
multi-column indexes on regular columns. Here the column to index does not exist in the
schema — it must be synthesised from a JSON expression.

---

## Schema design: adding a virtual generated column

```sql
-- Original table (metadata is opaque JSON)
CREATE TABLE events (
  id       TEXT PRIMARY KEY,
  ts       INTEGER NOT NULL,
  metadata TEXT    NOT NULL   -- e.g. {"userId":"u1","tier":"pro","region":"eu-west"}
);

-- Add virtual generated column extracted from JSON
ALTER TABLE events
  ADD COLUMN tier TEXT
  GENERATED ALWAYS AS (json_extract(metadata, '$.tier')) VIRTUAL;

-- Index the generated column
CREATE INDEX idx_events_tier ON events (tier);

-- Compound index for the common (tier, ts) filter + sort
CREATE INDEX idx_events_tier_ts ON events (tier, ts DESC);
```

After the migration, queries that filter on `tier` use the index automatically. You do not
need to change the insert logic — `tier` is computed at read time from `metadata`.

---

## Workers query patterns

```typescript
// D1 binding declared in wrangler.toml as [[d1_databases]]

interface Env {
  DB: D1Database;
}

interface Event {
  id: string;
  ts: number;
  metadata: string;
  tier: string; // virtual column, returned by SELECT *
}

// Before: full table scan on json_extract
async function getProEventsBefore(env: Env, before: number): Promise<Event[]> {
  const result = await env.DB.prepare(
    `SELECT * FROM events
     WHERE json_extract(metadata, '$.tier') = 'pro'
       AND ts < ?
     ORDER BY ts DESC
     LIMIT 100`
  )
    .bind(before)
    .all<Event>();
  return result.results;
}

// After: index seek on generated column — same SQL, faster plan
async function getProEventsAfterMigration(env: Env, before: number): Promise<Event[]> {
  const result = await env.DB.prepare(
    `SELECT * FROM events
     WHERE tier = 'pro'    -- generated column, hits idx_events_tier_ts
       AND ts < ?
     ORDER BY ts DESC
     LIMIT 100`
  )
    .bind(before)
    .all<Event>();
  return result.results;
}
```

Both queries are semantically equivalent; the second hits the index.

---

## Verifying the query plan with EXPLAIN

```typescript
async function explainQuery(env: Env): Promise<void> {
  const plan = await env.DB.prepare(
    `EXPLAIN QUERY PLAN
     SELECT * FROM events WHERE tier = 'pro' AND ts < 1700000000 ORDER BY ts DESC LIMIT 100`
  ).all();

  // Look for "USING INDEX idx_events_tier_ts" in the plan output
  console.log(JSON.stringify(plan.results, null, 2));
}
```

Expected output (indicates index use):
```
SEARCH events USING INDEX idx_events_tier_ts (tier=? AND ts<?)
```

If you still see `SCAN events` after adding the index, check that the query references the
generated column name (`tier`), not the `json_extract()` expression.

---

## Stored generated column for covering index patterns

If queries select additional columns that also appear in JSON, a STORED generated column
lets you build a covering index that avoids reading the `metadata` blob entirely.

```sql
-- Add stored generated column for region
ALTER TABLE events
  ADD COLUMN region TEXT
  GENERATED ALWAYS AS (json_extract(metadata, '$.region')) STORED;

-- Covering index: satisfies (tier, region, ts) lookup without touching metadata
CREATE INDEX idx_events_tier_region_ts ON events (tier, region, ts DESC)
  INCLUDE (id);  -- SQLite 3.37+: include PK to avoid rowid lookup
```

```typescript
// Covering index query — D1 does not need to fetch metadata column
const result = await env.DB.prepare(
  `SELECT id, tier, region, ts
   FROM events
   WHERE tier = 'pro' AND region = 'eu-west'
   ORDER BY ts DESC
   LIMIT 50`
).all<Pick<Event, 'id' | 'tier' | 'region' | 'ts'>>();
```

Note: STORED columns increase write amplification (the computed value is persisted on
every INSERT/UPDATE). For write-heavy tables, benchmark write throughput before committing.

---

## Migrating existing rows after adding a generated column

A VIRTUAL generated column is computed on the fly — existing rows gain the column
immediately with no backfill needed. An index built on a VIRTUAL generated column, however,
must be populated after creation:

```typescript
async function buildIndex(env: Env): Promise<void> {
  // D1 does not expose REINDEX; creating the index on an existing table
  // with data triggers an automatic full-table scan to build the B-tree.
  // For large tables (>100k rows), run during off-peak and monitor CPU time.
  await env.DB.exec(`CREATE INDEX IF NOT EXISTS idx_events_tier ON events (tier)`);
  console.log('Index created — existing rows now indexed');
}
```

D1 charges Class B reads for every row scanned during index creation. On a 1 M row table,
budget for ~1 000 Class B operations (D1 pages each holding ~100 rows).

---

## Array and nested JSON field indexing

For JSON arrays (e.g., `metadata = {"tags":["billing","export"]}`), `json_extract` returns
the first element with `$[0]`; full array search requires `json_each` which cannot be
directly indexed. A common pattern is to store a denormalized string version:

```sql
-- Generated column for first tag (limited but indexable)
ALTER TABLE events
  ADD COLUMN primary_tag TEXT
  GENERATED ALWAYS AS (json_extract(metadata, '$.tags[0]')) VIRTUAL;

CREATE INDEX idx_events_primary_tag ON events (primary_tag);
```

For multi-value tag search, maintain a separate junction table and keep JSON for
non-filterable metadata only.

---

## Anti-patterns

- **Indexing the raw `metadata` column.** An index on `TEXT` metadata is useless for JSON
  field filters because the comparison is on the whole serialised string.
- **Using `json_extract()` in a WHERE clause with no generated column.** This forces a
  full scan; any optimiser hint is ineffective because the expression is not in the schema.
- **Adding STORED columns to write-hot tables without benchmarking.** Every INSERT must
  compute and persist all STORED generated columns, doubling write I/O on the JSON blob
  if the blob is large.
- **Over-indexing extracted fields.** Each index adds latency to writes and increases D1
  storage. Index only fields actually used in WHERE or ORDER BY clauses.

---

## Gotchas

- D1 is built on SQLite; `ALTER TABLE … ADD COLUMN … GENERATED` was added in SQLite 3.31.
  D1 uses a recent SQLite version but the exact version is not contractually pinned.
  Validate syntax in `wrangler dev --local` before deploying.
- Generated column names must not conflict with explicit column names. If you add a
  generated column called `tier` and later the JSON schema changes so `$.tier` is removed,
  existing rows will return NULL from the generated column — queries that assume non-null
  `tier` will silently miss those rows.
- D1 `EXPLAIN QUERY PLAN` output is available in Workers but cannot be used in production
  queries — wrap `EXPLAIN` calls in a `__debug` route gated behind an auth check.
- The D1 `exec()` method is for schema DDL only and runs outside a prepared statement;
  it is subject to D1's 30-second query timeout but has no parameter binding.

---

## Verification

```bash
# Local verification with wrangler dev
wrangler d1 execute example project-db --local \
  --command "EXPLAIN QUERY PLAN SELECT * FROM events WHERE tier='pro' ORDER BY ts DESC LIMIT 10"

# Confirm index is listed
wrangler d1 execute example project-db --local \
  --command "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='events'"

# Measure query time before and after index creation
wrangler d1 execute example project-db \
  --command "SELECT COUNT(*) FROM events WHERE tier='pro'"
```

Compare `.meta.duration` in the D1 response before and after index creation to confirm
the speedup. Expect O(log n) access time after index creation vs. O(n) before.

---

## Related

- `d1-covering-index-multi-column.md`
- `d1-query-performance-explain-index.md`
- `d1-pragma-optimize-query-planner.md`
- `d1-prepared-statement-reuse.md`
- `d1-query-optimization.md`

---

## Sources

- SQLite generated columns: https://www.sqlite.org/gencol.html
- SQLite json_extract: https://www.sqlite.org/json1.html
- D1 query performance: https://developers.cloudflare.com/d1/best-practices/query-performance/
- D1 limits: https://developers.cloudflare.com/d1/platform/limits/
