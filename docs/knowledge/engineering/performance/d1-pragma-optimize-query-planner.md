# D1 PRAGMA optimize — Query Planner Statistics Refresh

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

After creating new indexes or loading a significant number of rows into a D1 database,
query performance does not improve as expected. `EXPLAIN QUERY PLAN` shows the query
planner still choosing a full table scan or selecting a suboptimal index even though a
better index exists. Alternatively, queries that were fast degrade after a bulk data
load because the planner's statistics no longer reflect the actual data distribution.

## Context

SQLite (which powers Cloudflare D1) chooses query execution plans using a cost-based
optimizer. The optimizer's decisions depend on statistics stored in the
`sqlite_stat1` table (and optionally `sqlite_stat2`/`sqlite_stat4`). These statistics
record the approximate number of rows per distinct value for each index, allowing the
planner to estimate selectivity.

The statistics are **not updated automatically** as rows are inserted, updated, or
deleted. They are populated by running `ANALYZE` (which scans every index) or the
lighter `PRAGMA optimize`, which selectively refreshes statistics only for tables and
indexes where the statistics are stale or absent.

Cloudflare D1 exposes the full SQLite pragma surface via the `db.prepare()` /
`db.exec()` interface, making `PRAGMA optimize` available to Workers.

`PRAGMA optimize` is preferable to `ANALYZE` in most cases:
- It analyzes only tables whose row count has changed significantly since the last
  analysis (roughly 4× change threshold).
- It returns immediately if statistics are already current, making it safe to call
  proactively without paying a full scan cost every time.
- `ANALYZE` always scans every table and index; it is appropriate after a one-time
  bulk load but too expensive to run per-request.

## Running PRAGMA optimize via Workers

```typescript
// worker/db-maintenance.ts
import type { D1Database } from "@cloudflare/workers-types";

/**
 * Refresh query planner statistics for tables with stale stats.
 * Safe to call proactively; no-ops if stats are current.
 */
export async function optimizeQueryPlanner(db: D1Database): Promise<void> {
  // PRAGMA optimize analyzes only stale tables. Pass 0x10002 to also
  // run on tables with no prior statistics (recommended after schema changes).
  await db.prepare("PRAGMA optimize=0x10002").run();
}
```

```typescript
// worker/handler.ts — run on a scheduled trigger, not on every request.
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await optimizeQueryPlanner(env.DB);
    console.log("Query planner statistics refreshed");
  },
};
```

## PRAGMA optimize Flags

The `PRAGMA optimize` accepts a bitmask argument (default `0xFFFE`):

| Flag     | Meaning                                                               |
|----------|-----------------------------------------------------------------------|
| `0x0001` | Debug mode — return a list of tables that would be analyzed, but do not analyze. |
| `0x0002` | Analyze tables with no prior stats (newly created tables or post-schema migrations). |
| `0x0010` | Run only one analysis step (useful inside hot paths; call iteratively). |
| `0x10000` | Analyze all tables regardless of staleness threshold (equivalent to ANALYZE). |

Recommended combination for post-migration maintenance: `0x10002` (include tables
with no prior stats + analyze stale tables).

```typescript
// Dry run: see which tables need analysis without touching stats.
const result = await db.prepare("PRAGMA optimize=0x0001").all();
console.log("Tables that need analysis:", result.results);
```

## Running ANALYZE After a Bulk Load

After a one-time bulk data import (e.g., seeding a product catalog), run `ANALYZE`
unconditionally to rebuild statistics from scratch:

```typescript
// worker/seed.ts
export async function bulkSeedAndAnalyze(
  db: D1Database,
  rows: ProductRow[]
): Promise<void> {
  // Batch-insert rows.
  const insert = db.prepare(
    "INSERT INTO products (id, name, category, price) VALUES (?, ?, ?, ?)"
  );

  const batches: D1PreparedStatement[][] = [];
  for (let i = 0; i < rows.length; i += 100) {
    batches.push(
      rows.slice(i, i + 100).map((r) =>
        insert.bind(r.id, r.name, r.category, r.price)
      )
    );
  }
  await Promise.all(batches.map((b) => db.batch(b)));

  // Rebuild statistics after bulk load.
  await db.exec("ANALYZE");
  console.log(`Seeded ${rows.length} rows and rebuilt query planner statistics`);
}
```

## Diagnosing Stale Statistics

Use `EXPLAIN QUERY PLAN` before and after running `PRAGMA optimize` to confirm the
planner switched to the expected index:

```typescript
// worker/diagnose.ts
export async function explainQueryPlan(
  db: D1Database,
  query: string,
  ...params: unknown[]
): Promise<void> {
  const plan = await db
    .prepare(`EXPLAIN QUERY PLAN ${query}`)
    .bind(...params)
    .all();

  console.log("Query plan:", JSON.stringify(plan.results, null, 2));
}

// Usage:
await explainQueryPlan(
  env.DB,
  "SELECT * FROM orders WHERE user_id = ? AND status = ? ORDER BY created_at DESC LIMIT 20",
  userId,
  "pending"
);
// After: should show "USING INDEX idx_orders_user_status_created"
// Before optimize: may show "SCAN orders"
```

## Scheduling Strategy

| Scenario                        | Recommended approach                        |
|---------------------------------|---------------------------------------------|
| Normal steady-state traffic     | `PRAGMA optimize` in a daily Cron Trigger   |
| Post-migration schema change    | `PRAGMA optimize=0x10002` immediately after |
| One-time bulk data import       | `ANALYZE` (full) immediately after import   |
| High-write table (>10k INS/day) | `PRAGMA optimize` in a 6-hour Cron Trigger  |
| Read-only replica databases     | No action needed (stats carried over)       |

```typescript
// wrangler.toml
// [triggers]
// crons = ["0 3 * * *"]   # 03:00 UTC daily
```

```typescript
// worker/index.ts
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    if (event.cron === "0 3 * * *") {
      await env.DB.prepare("PRAGMA optimize=0x10002").run();
    }
  },
};
```

## Anti-patterns

- **Running `ANALYZE` per-request**: `ANALYZE` scans every index in the database and
  can take hundreds of milliseconds on large databases. Never call it in a request
  handler.
- **Ignoring statistics after index creation**: Creating an index without running
  `PRAGMA optimize` or `ANALYZE` may leave the planner unaware of the index's
  selectivity. New indexes have no entry in `sqlite_stat1` until analysis runs.
- **Running `PRAGMA optimize` with `0x10000` (full analyze) routinely**: This
  defeats the adaptive benefit of `optimize` and behaves like `ANALYZE`. Reserve
  `0x10000` for post-migration or post-bulk-load scenarios.
- **Checking `sqlite_stat1` via raw query to determine freshness**: The staleness
  threshold is internal to SQLite and changes across versions. Use `PRAGMA
  optimize=0x0001` (debug mode) to let SQLite tell you which tables need analysis.

## Gotchas

- **D1 HTTP API vs. WebSocket API**: `PRAGMA optimize` uses the same D1 binding
  interface as regular queries. It incurs one HTTP round-trip per call to the D1
  backend. Ensure it runs in a background context (Cron Trigger, Queue consumer)
  where the Worker's 30-second CPU wall-clock limit is not a concern.
- **Statistics are per-database, not per-table-replication**: D1 replicates data
  across Cloudflare's global network. `sqlite_stat1` statistics are replicated with
  the data; running `ANALYZE` on the primary propagates updated statistics to
  read replicas automatically.
- **Effect is not instantaneous on read replicas**: After `ANALYZE` or `PRAGMA
  optimize` on the primary, read replica query plans update after the next
  replication cycle. Expect a short lag (typically seconds to a few minutes).
- **`PRAGMA optimize` is not a substitute for good schema design**: Statistics help
  the planner choose the best available index. If no suitable index exists, the
  planner's only option remains a full scan. Always profile with `EXPLAIN QUERY PLAN`
  and create appropriate indexes before relying on statistics.

## Verification

```typescript
// Before:
await explainQueryPlan(env.DB, "SELECT * FROM orders WHERE user_id = ? AND status = ?", uid, "pending");
// Expect: SCAN orders  (bad — no stats, planner doesn't know selectivity)

// Run:
await env.DB.prepare("PRAGMA optimize=0x10002").run();

// After:
await explainQueryPlan(env.DB, "SELECT * FROM orders WHERE user_id = ? AND status = ?", uid, "pending");
// Expect: SEARCH orders USING INDEX idx_orders_user_status  (good)
```

Optionally inspect `sqlite_stat1` directly to confirm statistics were written:

```typescript
const stats = await env.DB.prepare(
  "SELECT tbl, idx, stat FROM sqlite_stat1 WHERE tbl = 'orders'"
).all();
console.log("Index statistics:", stats.results);
// e.g., { tbl: "orders", idx: "idx_orders_user_status", stat: "50000 500 10" }
// "50000 rows total; 500 rows per unique user_id; 10 rows per unique (user_id, status)"
```

## Related

- `d1-query-performance-explain-index.md`
- `d1-query-optimization.md`
- `d1-prepared-statement-reuse.md`
- `d1-batch-query-performance-optimization.md`
- `d1-covering-index-multi-column.md`

## Sources

- SQLite PRAGMA optimize documentation: https://www.sqlite.org/pragma.html#pragma_optimize
- SQLite query planner statistics: https://www.sqlite.org/optoverview.html#statistics
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- SQLite ANALYZE: https://www.sqlite.org/lang_analyze.html
