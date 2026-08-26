# D1 ANALYZE and Query Planner Statistics in Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A D1 query that has a composite index is running a full table scan instead of using the index. `EXPLAIN QUERY PLAN` shows `SCAN table` where you expected `SEARCH table USING INDEX`. After a bulk data load or a major data shape change, queries that previously used indexes now choose suboptimal plans. You need to update SQLite's internal row-count statistics so the query planner makes accurate cost estimates.

---

## Context

SQLite's query planner uses statistics stored in the `sqlite_stat1` table (and optionally `sqlite_stat2`/`sqlite_stat3`/`sqlite_stat4`) to estimate the selectivity of each index. When a database is created or when data is first inserted, these tables are empty. The planner falls back to hard-coded heuristics — which can produce poor decisions when the actual distribution differs from the assumption. `ANALYZE` scans each table and index, writes fresh statistics to `sqlite_stat1`, and causes the planner to use those statistics for subsequent queries in the same connection.

D1 runs a stateless Worker per request, so statistics written by `ANALYZE` persist in the database file and are read by every new connection automatically. Running `ANALYZE` once (or on a schedule after bulk loads) improves plan quality for all subsequent requests.

`PRAGMA optimize` is a lighter-weight alternative that runs `ANALYZE` selectively on tables whose statistics appear stale, based on a change-count heuristic tracked in `sqlite_stat1`.

---

## Running ANALYZE After a Bulk Load

```typescript
// src/maintenance/analyze.ts
import type { D1Database } from '@cloudflare/workers-types';

/**
 * Run a full ANALYZE to refresh query-planner statistics.
 * Call once after bulk inserts / deletes that significantly change row counts.
 */
export async function analyzeDatabase(db: D1Database): Promise<void> {
  await db.prepare('ANALYZE').run();
}

/**
 * Analyze a specific table only — faster for large databases.
 */
export async function analyzeTable(
  db: D1Database,
  tableName: string
): Promise<void> {
  // Note: table names cannot be parameterised; validate before interpolating
  const safe = /^[a-z_][a-z0-9_]*$/i.test(tableName);
  if (!safe) throw new Error(`Invalid table name: ${tableName}`);
  await db.prepare(`ANALYZE ${tableName}`).run();
}
```

---

## Scheduled ANALYZE via Cron Trigger

```typescript
// src/worker.ts
import type { Env } from './types';
import { analyzeDatabase } from './maintenance/analyze';

export default {
  async scheduled(
    event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    ctx.waitUntil(analyzeDatabase(env.DB));
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml
[triggers]
crons = ["0 2 * * 0"]  # Weekly at 02:00 UTC Sunday
```

For databases that receive bulk loads on a regular schedule, trigger `ANALYZE` immediately after the load completes rather than waiting for the next cron window:

```typescript
// src/handlers/bulk-import.ts
export async function importDataset(
  db: D1Database,
  rows: Row[]
): Promise<void> {
  // 1. Bulk insert in batches
  const stmts = rows.map((r) =>
    db.prepare('INSERT INTO events (ts, type, payload) VALUES (?, ?, ?)').bind(
      r.ts, r.type, JSON.stringify(r.payload)
    )
  );
  for (let i = 0; i < stmts.length; i += 100) {
    await db.batch(stmts.slice(i, i + 100));
  }

  // 2. Refresh planner statistics immediately after load
  await analyzeTable(db, 'events');
}
```

---

## Using PRAGMA optimize as a Lighter Alternative

`PRAGMA optimize` analyses only tables that SQLite estimates have stale statistics (based on an internal query-count heuristic). It is safe to call on every request or every few minutes without significant overhead:

```typescript
// src/middleware/optimize.ts
/**
 * Run PRAGMA optimize at the start of each request.
 * SQLite skips ANALYZE if statistics appear fresh, so overhead is minimal.
 */
export async function maybePragmaOptimize(db: D1Database): Promise<void> {
  await db.prepare('PRAGMA optimize').run();
}
```

```typescript
// src/worker.ts — run optimize in fetch handler
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Run in background so it doesn't block the response
    ctx.waitUntil(maybePragmaOptimize(env.DB));
    return handleRequest(request, env);
  },
} satisfies ExportedHandler<Env>;
```

---

## Inspecting sqlite_stat1 Directly

```typescript
// src/debug/stats.ts
interface StatRow {
  tbl: string;
  idx: string | null;
  stat: string; // e.g. "12345 42 7" — row count, then average rows per distinct key
}

export async function getStatistics(db: D1Database): Promise<StatRow[]> {
  const { results } = await db
    .prepare('SELECT tbl, idx, stat FROM sqlite_stat1 ORDER BY tbl, idx')
    .all<StatRow>();
  return results;
}

export function parseStatRow(stat: string): number[] {
  return stat.split(' ').map(Number);
  // First number: total rows in table
  // Subsequent numbers: average rows per distinct value for each key column
}
```

```typescript
// Example output for a two-column index:
// stat = "50000 250 1"
// → 50,000 rows total; 250 average rows per distinct (col1); 1 row per (col1, col2)
```

---

## Verifying Plan Improvement After ANALYZE

```typescript
// src/debug/plan.ts
export async function explainQueryPlan(
  db: D1Database,
  sql: string
): Promise<string[]> {
  const { results } = await db
    .prepare(`EXPLAIN QUERY PLAN ${sql}`)
    .all<{ detail: string }>();
  return results.map((r) => r.detail);
}

// Usage: check before and after ANALYZE
export async function compareBeforeAfterAnalyze(db: D1Database): Promise<void> {
  const querySql =
    'SELECT * FROM events WHERE type = ? AND ts > ? ORDER BY ts DESC LIMIT 20';

  const planBefore = await explainQueryPlan(db, querySql);
  await analyzeDatabase(db);
  const planAfter = await explainQueryPlan(db, querySql);

  console.log('Before ANALYZE:', planBefore);
  console.log('After ANALYZE:', planAfter);
  // Expect: planAfter shows "SEARCH events USING INDEX idx_events_type_ts"
  // instead of "SCAN events"
}
```

---

## Resetting Statistics

If statistics become corrupted or you want to force a full re-baseline:

```typescript
export async function resetStatistics(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare('DELETE FROM sqlite_stat1'),
    db.prepare('ANALYZE'),
  ]);
}
```

---

## Anti-patterns

- **Never running ANALYZE after initial data load** — A fresh D1 database has no `sqlite_stat1` rows. The planner uses heuristics that assume balanced distributions. Run `ANALYZE` after seeding the database in CI/CD pipelines and after production bulk loads.
- **Running ANALYZE on every request** — `ANALYZE` scans every index. On a large database this can take hundreds of milliseconds and consume significant D1 CPU budget per request. Use `PRAGMA optimize` for per-request maintenance or a scheduled Cron for full ANALYZE.
- **Interpolating table names without validation** — `ANALYZE tableName` cannot use bound parameters. Always validate the table name against a strict allowlist or regex before interpolating it into the SQL string.
- **Expecting ANALYZE to fix a missing index** — `ANALYZE` helps the planner choose among existing indexes. It cannot create new indexes. If `EXPLAIN QUERY PLAN` shows a full scan and ANALYZE does not fix it, the required index may not exist.
- **Ignoring `sqlite_stat1` after truncating and re-inserting** — Truncating a table (DELETE FROM without WHERE) removes all rows but leaves stale statistics in `sqlite_stat1`. Run `ANALYZE` after a full table clear-and-reload.

---

## Gotchas

- `ANALYZE` acquires a shared lock during the scan and a reserved lock to write `sqlite_stat1`. In D1's WAL mode concurrent reads remain unblocked, but any concurrent write will briefly contend. Schedule ANALYZE during low-traffic periods for large tables.
- `PRAGMA optimize` is documented to run `ANALYZE` when the estimated number of rows examined since the last analysis exceeds a threshold (default ~1000 × index scan count). This threshold is not configurable in D1.
- Statistics are stored per database file. D1's read replicas receive the latest file state from the primary after replication lag; queries on replicas may use slightly stale statistics until the next file sync.
- `sqlite_stat2`, `sqlite_stat3`, and `sqlite_stat4` provide more granular histogram data but require `SQLITE_ENABLE_STAT4` compile-time flag. D1's SQLite build may or may not include this; assume only `sqlite_stat1` is available for portability.
- After `ANALYZE`, the planner picks up new statistics on the next statement prepared in the same connection. In D1's stateless Workers model, each request opens a fresh connection so updated statistics take effect immediately for all requests after the ANALYZE completes.

---

## Verification

```typescript
export async function verifyStatisticsExist(db: D1Database): Promise<void> {
  const { results } = await db
    .prepare('SELECT COUNT(*) AS cnt FROM sqlite_stat1')
    .all<{ cnt: number }>();

  const count = results[0]?.cnt ?? 0;
  if (count === 0) {
    console.warn('sqlite_stat1 is empty — run ANALYZE to populate statistics');
  } else {
    console.log(`sqlite_stat1 has ${count} entries`);
  }
}
```

```sql
-- Manually inspect statistics for a specific table
SELECT tbl, idx, stat
FROM sqlite_stat1
WHERE tbl = 'events'
ORDER BY idx;
```

---

## Related

- `d1-sqlite-query-optimization.md`
- `sqlite-pragma-optimize-maintenance-budget.md`
- `explain-analyze-reading.md`
- `d1-vacuum-incremental-maintenance-workers.md`
- `composite-index-design.md`

---

## Sources

- https://www.sqlite.org/lang_analyze.html
- https://www.sqlite.org/pragma.html#pragma_optimize
- https://www.sqlite.org/optoverview.html#statistics
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
