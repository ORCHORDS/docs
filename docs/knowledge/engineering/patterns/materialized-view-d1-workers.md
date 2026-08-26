# Materialized View Pattern with D1 and Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your `/dashboard` endpoint runs a 12-table JOIN with several GROUP BY clauses
to compute per-tenant aggregate statistics. On a D1 database with millions of
rows, this query takes 300–800 ms. It fires on every page load. Response times
are poor and D1 row-read costs are accumulating.

The underlying data changes infrequently (once per minute at most). You do not
need real-time results — 60-second-old aggregates are acceptable.

---

## Context

A **materialized view** is a pre-computed query result stored in a table.
Instead of running the expensive JOIN on every request, a background process
re-runs it on a schedule and persists the results. Read paths query the
materialized table, which is a trivial primary-key lookup.

SQLite (and therefore D1) does not support native materialized views with
automatic refresh. You implement the refresh yourself using:

- A **Cron Trigger Worker** that runs the expensive query and writes the result
  to a `mv_*` table.
- Or a **Durable Object alarm** for precise sub-minute scheduling.

The read path is a plain `SELECT` against the `mv_*` table — typically
single-digit milliseconds.

---

## Schema Design

```sql
-- migrations/003_materialized_views.sql

-- Source tables (simplified)
CREATE TABLE IF NOT EXISTS events (
  id         TEXT    PRIMARY KEY,
  tenant_id  TEXT    NOT NULL,
  event_type TEXT    NOT NULL,
  revenue    INTEGER NOT NULL DEFAULT 0,  -- in cents
  created_at INTEGER NOT NULL
);

-- Materialized view table: one row per tenant, refreshed by the cron job
CREATE TABLE IF NOT EXISTS mv_tenant_stats (
  tenant_id        TEXT    PRIMARY KEY,
  event_count      INTEGER NOT NULL DEFAULT 0,
  total_revenue    INTEGER NOT NULL DEFAULT 0,  -- cents
  last_event_at    INTEGER,
  refreshed_at     INTEGER NOT NULL  -- when this row was last computed
);

-- Track refresh metadata for observability
CREATE TABLE IF NOT EXISTS mv_refresh_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  view_name    TEXT    NOT NULL,
  started_at   INTEGER NOT NULL,
  finished_at  INTEGER,
  rows_written INTEGER,
  error        TEXT
);
```

---

## Refresh Worker (Cron Trigger)

```typescript
// src/refresh/tenant-stats-refresh.ts
import { Env } from '../types';

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await refreshTenantStats(env);
  },
};

async function refreshTenantStats(env: Env): Promise<void> {
  const startedAt = Date.now();
  const logId = await startRefreshLog('mv_tenant_stats', startedAt, env);

  try {
    // 1. Compute aggregates from the source table
    //    This is the expensive query — run once per cron tick, not per request
    const { results: aggregates } = await env.DB.prepare(`
      SELECT
        tenant_id,
        COUNT(*)           AS event_count,
        SUM(revenue)       AS total_revenue,
        MAX(created_at)    AS last_event_at
      FROM events
      WHERE created_at > ?
      GROUP BY tenant_id
    `).bind(Date.now() - 7 * 24 * 60 * 60 * 1000).all<AggregateRow>();

    if (aggregates.length === 0) {
      await finishRefreshLog(logId, 0, null, env);
      return;
    }

    // 2. Upsert into the materialized view table in batches
    //    D1 batch() is limited to 100 statements per call
    const batchSize = 90;
    const refreshedAt = Date.now();

    for (let i = 0; i < aggregates.length; i += batchSize) {
      const chunk = aggregates.slice(i, i + batchSize);
      await env.DB.batch(
        chunk.map((row) =>
          env.DB.prepare(`
            INSERT INTO mv_tenant_stats
              (tenant_id, event_count, total_revenue, last_event_at, refreshed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id) DO UPDATE SET
              event_count   = excluded.event_count,
              total_revenue = excluded.total_revenue,
              last_event_at = excluded.last_event_at,
              refreshed_at  = excluded.refreshed_at
          `).bind(
            row.tenant_id,
            row.event_count,
            row.total_revenue,
            row.last_event_at,
            refreshedAt,
          )
        )
      );
    }

    await finishRefreshLog(logId, aggregates.length, null, env);

  } catch (err) {
    await finishRefreshLog(logId, 0, String(err), env);
    throw err; // re-throw so Cloudflare marks the cron invocation as failed
  }
}

async function startRefreshLog(
  viewName: string,
  startedAt: number,
  env: Env,
): Promise<number> {
  const result = await env.DB.prepare(
    `INSERT INTO mv_refresh_log (view_name, started_at) VALUES (?, ?) RETURNING id`
  ).bind(viewName, startedAt).first<{ id: number }>();
  return result!.id;
}

async function finishRefreshLog(
  id: number,
  rowsWritten: number,
  error: string | null,
  env: Env,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE mv_refresh_log SET finished_at = ?, rows_written = ?, error = ? WHERE id = ?`
  ).bind(Date.now(), rowsWritten, error, id).run();
}

interface AggregateRow {
  tenant_id: string;
  event_count: number;
  total_revenue: number;
  last_event_at: number | null;
}
```

```toml
# wrangler.toml
[triggers]
crons = ["* * * * *"]   # Every minute; adjust to match acceptable staleness
```

---

## Read Path (Fast Lookup)

```typescript
// src/handlers/dashboard.ts

export async function getDashboardStats(
  tenantId: string,
  env: Env,
): Promise<Response> {
  // Fast primary-key lookup — typically < 5 ms on D1
  const stats = await env.DB.prepare(`
    SELECT
      tenant_id,
      event_count,
      total_revenue,
      last_event_at,
      refreshed_at
    FROM mv_tenant_stats
    WHERE tenant_id = ?
  `).bind(tenantId).first<TenantStats>();

  if (!stats) {
    return Response.json({ tenantId, event_count: 0, total_revenue: 0, refreshed_at: null });
  }

  const ageSeconds = Math.floor((Date.now() - stats.refreshed_at) / 1000);

  return Response.json(stats, {
    headers: {
      'X-Data-Age-Seconds': String(ageSeconds),
      // Tell clients the data may be up to 60s stale
      'Cache-Control': 'public, max-age=30, stale-while-revalidate=60',
    },
  });
}

interface TenantStats {
  tenant_id: string;
  event_count: number;
  total_revenue: number;
  last_event_at: number | null;
  refreshed_at: number;
}
```

---

## Sub-minute Refresh via Durable Object Alarms

Cloudflare Cron Triggers fire at most once per minute. For shorter refresh
intervals (e.g. 10 seconds), use a Durable Object alarm:

```typescript
// src/objects/RefreshSchedulerDO.ts

export class RefreshSchedulerDO implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {
    // Schedule the first alarm immediately on construction
    this.state.blockConcurrencyWhile(async () => {
      const existing = await this.state.storage.getAlarm();
      if (!existing) {
        await this.state.storage.setAlarm(Date.now() + 10_000); // 10 s
      }
    });
  }

  async alarm(): Promise<void> {
    try {
      await refreshTenantStats(this.env);
    } finally {
      // Schedule the next alarm 10 s from now
      await this.state.storage.setAlarm(Date.now() + 10_000);
    }
  }

  async fetch(_request: Request): Promise<Response> {
    return new Response('Refresh scheduler running');
  }
}
```

Start the DO once at deploy time (or via an init endpoint); after that it
self-reschedules indefinitely.

---

## Partial Refresh (Incremental Update)

For very large datasets, refreshing all tenants on every tick is wasteful. Track
a high-watermark cursor to refresh only rows that changed since the last run:

```typescript
async function incrementalRefresh(env: Env): Promise<void> {
  // Read the watermark from KV (survives Worker restarts)
  const watermarkStr = await env.KV.get('mv:tenant_stats:watermark');
  const watermark = watermarkStr ? parseInt(watermarkStr, 10) : 0;
  const now = Date.now();

  const { results } = await env.DB.prepare(`
    SELECT tenant_id, COUNT(*) AS event_count, SUM(revenue) AS total_revenue,
           MAX(created_at) AS last_event_at
    FROM events
    WHERE created_at > ? AND created_at <= ?
    GROUP BY tenant_id
  `).bind(watermark, now).all<AggregateRow>();

  // Upsert changed tenants only
  if (results.length > 0) {
    await env.DB.batch(results.map((row) =>
      env.DB.prepare(`
        INSERT INTO mv_tenant_stats (tenant_id, event_count, total_revenue, last_event_at, refreshed_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (tenant_id) DO UPDATE SET
          event_count   = mv_tenant_stats.event_count + excluded.event_count,
          total_revenue = mv_tenant_stats.total_revenue + excluded.total_revenue,
          last_event_at = MAX(mv_tenant_stats.last_event_at, excluded.last_event_at),
          refreshed_at  = excluded.refreshed_at
      `).bind(row.tenant_id, row.event_count, row.total_revenue, row.last_event_at, now)
    ));
  }

  // Advance the watermark
  await env.KV.put('mv:tenant_stats:watermark', String(now));
}
```

---

## Anti-patterns

**Reading from the source tables directly in the hot path**
If a JOIN across several large tables takes 500 ms, moving it to the read path
only pushes the problem to production traffic. Always move expensive aggregations
to the refresh job.

**Using a single upsert for the entire dataset in one batch()**
D1 `batch()` is limited to 100 statements per call. Chunking is required for
materialized views covering more than ~90 tenants.

**Not logging `refreshed_at`**
Without a `refreshed_at` column, the read path cannot tell clients how stale the
data is. Expose it in the response body or as an HTTP header.

**Refreshing on every write (eager materialization)**
If writes are frequent, an eager refresh triggers expensive queries too often.
Use lazy/scheduled refresh unless the data must be real-time, in which case a
live query is the right approach.

---

## Gotchas

- **D1 row read costs**: The expensive aggregation query in the refresh job reads
  many rows and incurs D1 billing costs on each tick. Track `rows_read` in
  `mv_refresh_log` and optimize the source query (indexes, date partitioning)
  to minimize reads.

- **Cron granularity**: Cloudflare Cron Triggers support at most 1-minute
  intervals on the Free plan. Use DO alarms for sub-minute refresh on any plan.

- **First-request cold materialization**: On a freshly deployed database with
  no `mv_*` rows, the first request returns empty data until the cron fires.
  Pre-seed with a deploy hook or an init Worker that calls the refresh function
  once on startup.

- **Incremental accumulation drift**: The additive incremental refresh
  (`event_count + excluded.event_count`) can drift if events are deleted or
  corrected. Schedule a full refresh (e.g. daily) to reconcile.

---

## Verification

```bash
# 1. Confirm source table has data
wrangler d1 execute MY_DB --command "SELECT COUNT(*) FROM events"

# 2. Trigger cron manually in local dev
wrangler dev --test-scheduled

# 3. Check materialized view was populated
wrangler d1 execute MY_DB --command \
  "SELECT tenant_id, event_count, total_revenue, refreshed_at FROM mv_tenant_stats LIMIT 5"

# 4. Time the read path
time curl https://api.example.com/dashboard?tenantId=tenant_001

# 5. Compare to un-materialized query time
wrangler d1 execute MY_DB --command \
  "EXPLAIN QUERY PLAN SELECT tenant_id, COUNT(*), SUM(revenue) FROM events GROUP BY tenant_id"

# 6. Check refresh log for errors
wrangler d1 execute MY_DB --command \
  "SELECT * FROM mv_refresh_log ORDER BY started_at DESC LIMIT 10"
```

---

## Related

- `request-coalescing-cache-stampede.md` — cache materialized-view results in
  KV or the Cache API to avoid even the primary-key lookup on every request.
- `cron-scheduling.md` — Cloudflare Cron Trigger configuration and limitations.
- `event-sourcing-cloudflare-workers-d1.md` — when the source data is an
  append-only event log, materialized views are the primary read model.
- `cache-aside-kv-d1-fallback.md` — an alternative read pattern: cache in KV,
  fall back to D1 on miss.
- `database-index-strategies.md` — ensuring the source table queries used in
  the refresh job are indexed appropriately.

---

## Sources

- PostgreSQL documentation — Materialized Views:
  https://www.postgresql.org/docs/current/rules-materializedviews.html
- Cloudflare D1 documentation:
  https://developers.cloudflare.com/d1/
- Cloudflare Durable Object alarms:
  https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare Cron Triggers:
  https://developers.cloudflare.com/workers/configuration/cron-triggers/
- SQLite ON CONFLICT clause:
  https://www.sqlite.org/lang_conflict.html
