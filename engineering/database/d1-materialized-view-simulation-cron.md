# D1 Materialized View Simulation with Workers Cron Triggers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Expensive aggregation queries — leaderboards, daily summaries, cohort counts — run on every API request and account for the majority of D1 read latency. D1 (SQLite) has no native `CREATE MATERIALIZED VIEW`, so there is no built-in way to pre-compute and cache the results at the database level. Dashboard endpoints slow down as data grows.

## Context

The standard workaround is a "summary table" pattern: a real table that stores pre-computed aggregates, refreshed on a schedule via a Cloudflare Workers Cron Trigger (a `scheduled` handler). The summary table is read directly by API request handlers — query cost drops from O(rows) to O(1). A `refresh_log` table tracks when each summary was last rebuilt, so stale-data bugs surface in monitoring. The cron handler runs in a separate Workers invocation and is not on the critical path of user requests.

## Schema: Summary Table and Refresh Log

```sql
-- migrations/0015_leaderboard_summary.sql
CREATE TABLE IF NOT EXISTS leaderboard_daily (
  game_id     INTEGER NOT NULL,
  user_id     INTEGER NOT NULL,
  score       INTEGER NOT NULL,
  rank        INTEGER NOT NULL,
  computed_at TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (game_id, rank)
);

CREATE TABLE IF NOT EXISTS order_stats_daily (
  stat_date      TEXT    NOT NULL PRIMARY KEY,   -- 'YYYY-MM-DD'
  order_count    INTEGER NOT NULL DEFAULT 0,
  gross_cents    INTEGER NOT NULL DEFAULT 0,
  unique_buyers  INTEGER NOT NULL DEFAULT 0,
  computed_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS summary_refresh_log (
  summary_name TEXT NOT NULL,
  started_at   TEXT NOT NULL,
  finished_at  TEXT,
  status       TEXT NOT NULL DEFAULT 'running',  -- running | ok | error
  error_msg    TEXT,
  PRIMARY KEY (summary_name, started_at)
);
```

## Cron Handler: Refresh Logic

```typescript
// src/cron.ts
import type { D1Database, ScheduledEvent, ExecutionContext } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

// ---------------------------------------------------------------------------
// Leaderboard refresh
// ---------------------------------------------------------------------------
async function refreshLeaderboard(db: D1Database, gameId: number): Promise<void> {
  // Recompute top 100 for a given game, rank with RANK() window function
  await db.batch([
    db.prepare(`DELETE FROM leaderboard_daily WHERE game_id = ?`).bind(gameId),

    db.prepare(
      `INSERT INTO leaderboard_daily (game_id, user_id, score, rank, computed_at)
       SELECT
         ?1 AS game_id,
         user_id,
         SUM(score_delta)                              AS score,
         RANK() OVER (ORDER BY SUM(score_delta) DESC) AS rank,
         datetime('now')
       FROM game_events
       WHERE game_id = ?1
         AND event_time >= datetime('now', '-1 day')
       GROUP BY user_id
       ORDER BY score DESC
       LIMIT 100`
    ).bind(gameId),
  ]);
}

// ---------------------------------------------------------------------------
// Order stats refresh — rolling 90 days
// ---------------------------------------------------------------------------
async function refreshOrderStats(db: D1Database): Promise<void> {
  await db.batch([
    // Delete stats older than 90 days (keep rolling window)
    db.prepare(
      `DELETE FROM order_stats_daily
       WHERE stat_date < date('now', '-90 days')`
    ),

    // Upsert stats for the last 7 days (catch late-arriving orders)
    db.prepare(
      `INSERT INTO order_stats_daily (stat_date, order_count, gross_cents, unique_buyers, computed_at)
       SELECT
         date(created_at)       AS stat_date,
         COUNT(*)               AS order_count,
         SUM(total_cents)       AS gross_cents,
         COUNT(DISTINCT user_id) AS unique_buyers,
         datetime('now')
       FROM orders
       WHERE created_at >= date('now', '-7 days')
       GROUP BY date(created_at)
       ON CONFLICT (stat_date) DO UPDATE SET
         order_count   = excluded.order_count,
         gross_cents   = excluded.gross_cents,
         unique_buyers = excluded.unique_buyers,
         computed_at   = excluded.computed_at`
    ),
  ]);
}

// ---------------------------------------------------------------------------
// Wrapper: log start/finish/error
// ---------------------------------------------------------------------------
async function runRefresh(
  db: D1Database,
  name: string,
  fn: () => Promise<void>
): Promise<void> {
  const startedAt = new Date().toISOString();
  await db.prepare(
    `INSERT INTO summary_refresh_log (summary_name, started_at, status)
     VALUES (?, ?, 'running')`
  ).bind(name, startedAt).run();

  try {
    await fn();
    await db.prepare(
      `UPDATE summary_refresh_log
       SET finished_at = datetime('now'), status = 'ok'
       WHERE summary_name = ? AND started_at = ?`
    ).bind(name, startedAt).run();
  } catch (err) {
    await db.prepare(
      `UPDATE summary_refresh_log
       SET finished_at = datetime('now'), status = 'error', error_msg = ?
       WHERE summary_name = ? AND started_at = ?`
    ).bind(String(err), name, startedAt).run();
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Exported scheduled handler
// ---------------------------------------------------------------------------
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    // Run refreshes; continue others even if one fails
    const results = await Promise.allSettled([
      runRefresh(env.DB, 'leaderboard_game_1', () => refreshLeaderboard(env.DB, 1)),
      runRefresh(env.DB, 'order_stats_daily',  () => refreshOrderStats(env.DB)),
    ]);

    for (const r of results) {
      if (r.status === 'rejected') {
        console.error('Summary refresh failed:', r.reason);
      }
    }
  },
};
```

## Reading from the Summary Table in API Handlers

```typescript
// src/api.ts
export async function getLeaderboard(
  env: Env,
  gameId: number,
  limit = 20
): Promise<Array<{ rank: number; user_id: number; score: number; computed_at: string }>> {
  const { results } = await env.DB.prepare(
    `SELECT rank, user_id, score, computed_at
     FROM leaderboard_daily
     WHERE game_id = ?
     ORDER BY rank
     LIMIT ?`
  )
    .bind(gameId, limit)
    .all<{ rank: number; user_id: number; score: number; computed_at: string }>();

  return results;
}

export async function getOrderStatsSummary(env: Env, days = 30) {
  const { results } = await env.DB.prepare(
    `SELECT stat_date, order_count, gross_cents, unique_buyers, computed_at
     FROM order_stats_daily
     WHERE stat_date >= date('now', ?||' days')
     ORDER BY stat_date DESC`
  )
    .bind(-days)
    .all<{
      stat_date: string;
      order_count: number;
      gross_cents: number;
      unique_buyers: number;
      computed_at: string;
    }>();

  return results;
}
```

## Anti-patterns

- Refreshing the summary table inside a request handler on a cache miss — moves the expensive query back onto the critical path and under concurrent load causes thundering-herd re-computation.
- Dropping and recreating the summary table in a single non-batched sequence — leaves a window where API reads return zero rows; always `DELETE` + `INSERT` or use `UPSERT` inside a single `batch()` call.
- Scheduling the cron more frequently than D1 write latency allows for the refresh query — if the refresh takes 800 ms and the cron fires every minute, concurrent refresh runs will queue behind the D1 serialisation lock.

## Gotchas

- Workers Cron Triggers have a maximum execution time of 30 seconds (CPU time); very large aggregations may need to be broken into multiple cron jobs or chunked across invocations.
- The `scheduled` handler has no HTTP response — errors are only observable via `summary_refresh_log` or Cloudflare Workers logs; set up a log drain or alert on `status = 'error'` rows.
- `wrangler.toml` cron syntax uses 5-field UTC cron; `0 * * * *` runs at the top of every hour. Test locally with `wrangler dev --test-scheduled`.

## Verification

```bash
# Trigger the scheduled handler manually in dev
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"

# Check refresh log after a run
wrangler d1 execute MY_DB --remote \
  --command "SELECT * FROM summary_refresh_log ORDER BY started_at DESC LIMIT 10;"

# Confirm leaderboard populated
wrangler d1 execute MY_DB --remote \
  --command "SELECT COUNT(*) AS rows FROM leaderboard_daily WHERE game_id = 1;"
```

## Related

- `database/materialized-view-refresh.md`
- `database/d1-time-series-partitioning.md`
- `database/d1-window-functions-analytics.md`
- `database/d1-batch-operations-performance.md`
- `database/time-series-data-cloudflare-analytics-engine.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://www.sqlite.org/windowfunctions.html
