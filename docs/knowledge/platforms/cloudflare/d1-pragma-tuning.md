# d1-pragma-tuning

**Issue:** D1 PRAGMA tuning — performance, journal mode
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your D1 query is slow. You look at the plan. The table
scan is taking forever. You add an index. Still slow.
You wish there were more knobs.

## Root cause
**D1 supports PRAGMAs for tuning.** Use them
judiciously.

**Source:** SQLite PRAGMA docs.

## The "PRAGMA" pattern

PRAGMA is SQLite's way to set options:
```sql
PRAGMA journal_mode = WAL;
PRAGMA cache_size = -20000;  -- 20MB
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
```

The PRAGMA changes the DB behavior.

## The "WAL mode" pattern

For WAL (Write-Ahead Logging):
- **Pros:** Concurrent reads + writes
- **Cons:** Slightly more disk

```sql
PRAGMA journal_mode = WAL;
```

WAL is enabled.

## The "cache_size" pattern

For cache:
```sql
PRAGMA cache_size = -20000;  -- 20MB (negative = KB)
```

The cache is set.

## The "synchronous" pattern

For synchronous:
- **FULL:** Safest, slowest
- **NORMAL:** Safe + fast
- **OFF:** Fast, unsafe on crash

```sql
PRAGMA synchronous = NORMAL;
```

NORMAL is the right balance.

## The "temp_store" pattern

For temp_store:
- **DEFAULT:** File
- **FILE:** File
- **MEMORY:** RAM (faster)

```sql
PRAGMA temp_store = MEMORY;
```

Temp tables in memory.

## The "D1 PRAGMA" caveat

D1 doesn't expose all PRAGMAs:
- **Supported:** `cache_size`, `journal_mode` (read-only
  on replicas), etc.
- **Not supported:** Some DDL PRAGMAs

Check the docs for the supported list.

**Source:** D1 PRAGMA:
https://developers.cloudflare.com/d1/

## The "query plan" pattern

For the query plan:
```sql
EXPLAIN QUERY PLAN
SELECT * FROM users WHERE email = 'alice@example.com';
```

The plan is visible.

## The "ANALYZE" pattern

For ANALYZE (refresh stats):
```sql
ANALYZE;
```

The stats are refreshed.

## The "index" pattern

For indexes:
```sql
CREATE INDEX idx_users_email ON users(email);
```

The index is created.

## The "covering index" pattern

For a covering index (the query is satisfied by the
index):
```sql
CREATE INDEX idx_users_email_displayname ON users(email, displayName);
```

The query is faster.

## The "VACUUM" pattern

For VACUUM (reclaim space):
```sql
VACUUM;
```

The DB is compacted.

## The "D1 metrics" pattern

For D1 metrics:
- **Query count:** Number of queries
- **Query latency:** p50, p95, p99
- **Rows read:** Number of rows
- **Rows written:** Number of rows
- **DB size:** Storage

The metrics are in the CF dashboard.

## The "D1 anti-pattern" anti-patterns

### 1. SELECT *
- **Issue:** Reads all columns
- **Fix:** Select only what's needed

### 2. No index
- **Issue:** Full table scan
- **Fix:** Add index

### 3. Large UPDATE
- **Issue:** Locks the table
- **Fix:** Batch

### 4. No ANALYZE
- **Issue:** Stats are stale
- **Fix:** Run ANALYZE

### 5. Unused index
- **Issue:** Slows writes
- **Fix:** Drop

## Verification
- **Test:** EXPLAIN shows the index is used
- **Test:** Query is fast
- **Live:** D1 metrics are monitored
- **Audit:** Quarterly review

## Gotchas
- **The "SELECT *" anti-pattern.** Select only what's
  needed.
- **The "no index" anti-pattern.** Add an index.
- **The "no ANALYZE" anti-pattern.** Run ANALYZE.

## Related
- `cloudflare/d1-migration-best-practices.md`
- `cloudflare/d1-batch-bundler-bug.md`
- `database-index-strategies.md`
- `feature-cookbook-data-modeling.md`
- SQLite PRAGMA: https://www.sqlite.org/pragma.html
- D1 docs: https://developers.cloudflare.com/d1/
