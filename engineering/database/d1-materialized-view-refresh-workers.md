# Manual Materialized Views in D1 with Workers Cron

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Dashboard queries that aggregate millions of rows (`SUM`, `COUNT`, `AVG` grouped by day) are too slow to run on every HTTP request. D1 has no native materialized views, so you need a pattern that pre-computes results and refreshes them on a schedule.

## Context

SQLite (and therefore D1) does not support `CREATE MATERIALIZED VIEW`. The solution is to maintain an ordinary table that acts as a materialized view: a Workers Cron Trigger deletes stale rows and re-inserts freshly computed aggregates inside a single transaction. A `refreshed_at` column lets consumers know how fresh the data is.

---

## Schema

```sql
-- Source fact table
CREATE TABLE IF NOT EXISTS orders (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL,
  amount     REAL    NOT NULL,
  status     TEXT    NOT NULL DEFAULT 'pending',
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

-- Materialized view: daily revenue stats
CREATE TABLE IF NOT EXISTS mv_daily_stats (
  stat_date      TEXT    PRIMARY KEY,   -- 'YYYY-MM-DD'
  total_orders   INTEGER NOT NULL,
  total_revenue  REAL    NOT NULL,
  avg_order      REAL    NOT NULL,
  completed      INTEGER NOT NULL,
  refreshed_at   TEXT    NOT NULL
);
```

---

## Refresh Logic

The core pattern: compute aggregates from the source table, then atomically replace the materialized view rows inside a transaction.

```typescript
// src/refresh.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface DailyStat {
  stat_date:     string;
  total_orders:  number;
  total_revenue: number;
  avg_order:     number;
  completed:     number;
}

/**
 * Refresh the mv_daily_stats table.
 * @param db       D1 binding
 * @param lookback How many past days to recompute (default: 7 to catch late inserts)
 */
export async function refreshDailyStats(
  db: D1Database,
  lookback = 7
): Promise<{ rowsRefreshed: number; durationMs: number }> {
  const t0 = Date.now();

  // Step 1: Compute fresh aggregates
  const { results: freshRows } = await db
    .prepare(
      `SELECT
         date(created_at)                       AS stat_date,
         COUNT(*)                               AS total_orders,
         SUM(amount)                            AS total_revenue,
         AVG(amount)                            AS avg_order,
         SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed
       FROM orders
       WHERE created_at >= date('now', ? || ' days')
       GROUP BY date(created_at)
       ORDER BY stat_date`
    )
    .bind(`-${lookback}`)
    .all<DailyStat>();

  if (freshRows.length === 0) {
    return { rowsRefreshed: 0, durationMs: Date.now() - t0 };
  }

  const now = new Date().toISOString();

  // Step 2: Atomic swap inside a transaction
  const stmts = [
    // Delete old rows for the lookback window
    db.prepare(
      `DELETE FROM mv_daily_stats
       WHERE stat_date >= date('now', ? || ' days')`
    ).bind(`-${lookback}`),

    // Insert fresh rows
    ...freshRows.map((row) =>
      db
        .prepare(
          `INSERT INTO mv_daily_stats
             (stat_date, total_orders, total_revenue, avg_order, completed, refreshed_at)
           VALUES (?, ?, ?, ?, ?, ?)`
        )
        .bind(
          row.stat_date,
          row.total_orders,
          row.total_revenue,
          row.avg_order,
          row.completed,
          now
        )
    ),
  ];

  await db.batch(stmts);

  return { rowsRefreshed: freshRows.length, durationMs: Date.now() - t0 };
}
```

---

## Staleness Tracking

Consumers can check `refreshed_at` to decide whether to display a "data may be stale" banner.

```typescript
// src/query.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface StatRow {
  stat_date:     string;
  total_orders:  number;
  total_revenue: number;
  avg_order:     number;
  completed:     number;
  refreshed_at:  string;
}

export async function getDailyStats(
  db: D1Database,
  days = 30
): Promise<{ rows: StatRow[]; staleMinutes: number | null }> {
  const { results } = await db
    .prepare(
      `SELECT * FROM mv_daily_stats
       WHERE stat_date >= date('now', ? || ' days')
       ORDER BY stat_date DESC`
    )
    .bind(`-${days}`)
    .all<StatRow>();

  let staleMinutes: number | null = null;
  if (results.length > 0) {
    const lastRefresh = new Date(results[0].refreshed_at);
    staleMinutes = Math.floor((Date.now() - lastRefresh.getTime()) / 60_000);
  }

  return { rows: results, staleMinutes };
}
```

---

## Cron Worker

```typescript
// src/worker.ts
import { refreshDailyStats } from './refresh';
import { getDailyStats } from './query';

export interface Env {
  DB: D1Database;
}

export default {
  // HTTP handler for dashboard reads
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/stats') {
      const data = await getDailyStats(env.DB);
      return Response.json(data);
    }

    // Manual refresh trigger (protect with auth in production)
    if (url.pathname === '/admin/refresh' && req.method === 'POST') {
      const result = await refreshDailyStats(env.DB);
      return Response.json(result);
    }

    return new Response('Not found', { status: 404 });
  },

  // Cron: refresh every hour
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const result = await refreshDailyStats(env.DB, 7);
    console.log('[cron] mv_daily_stats refreshed', result);
  },
};
```

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id   = "<YOUR_DB_ID>"

[triggers]
crons = ["0 * * * *"]   # every hour at :00
```

---

## Full Refresh (Rebuild from Scratch)

For a complete rebuild (schema change, data correction), truncate and recompute all history:

```sql
-- Run via wrangler d1 execute or a one-off Worker endpoint
DELETE FROM mv_daily_stats;

INSERT INTO mv_daily_stats (stat_date, total_orders, total_revenue, avg_order, completed, refreshed_at)
SELECT
  date(created_at)                                          AS stat_date,
  COUNT(*)                                                  AS total_orders,
  SUM(amount)                                               AS total_revenue,
  AVG(amount)                                               AS avg_order,
  SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)    AS completed,
  datetime('now')                                           AS refreshed_at
FROM orders
GROUP BY date(created_at);
```

---

## Anti-patterns

- **Replacing the whole table on every cron** — rebuilding years of history each hour wastes CPU and can exceed the 30-second Cron Trigger wall-clock limit. Use a rolling `lookback` window.
- **Reading directly from `orders` on every dashboard request** — defeats the purpose; always query `mv_daily_stats`.
- **No transaction wrapping** — a crashed mid-refresh leaves partial rows; `db.batch()` ensures atomicity.

---

## Gotchas

- `db.batch()` in D1 runs statements sequentially inside one implicit transaction. If any statement fails, all preceding statements in the batch are rolled back.
- Late-arriving rows (inserted with a past `created_at`) won't be reflected until the next refresh of the window that covers that date. Size `lookback` accordingly.
- D1 Cron Triggers are best-effort; don't rely on them for sub-minute freshness. Use on-demand `/admin/refresh` for SLA-sensitive dashboards.

---

## Verification

```bash
# Check last refresh time
wrangler d1 execute MY_DB \
  --command "SELECT stat_date, total_orders, refreshed_at FROM mv_daily_stats ORDER BY stat_date DESC LIMIT 5;"

# Force a refresh
curl -X POST https://my-worker.example.com/admin/refresh
# {"rowsRefreshed":7,"durationMs":43}

# Confirm counts match source
wrangler d1 execute MY_DB \
  --command "SELECT date(created_at), COUNT(*) FROM orders GROUP BY 1 ORDER BY 1 DESC LIMIT 5;"
```

---

## Related

- `d1-archive-hot-cold-partition.md` — moving old rows to an archive table
- `d1-optimistic-locking-version-column.md` — safe concurrent writes to the source table
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/

## Sources

- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite aggregate functions: https://www.sqlite.org/lang_aggfunc.html
