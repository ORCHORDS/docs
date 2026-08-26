# Time-Series Rollup Aggregation Pattern — D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You store raw events (page views, API calls, IoT readings) in a D1 table. Over time the table grows to tens of millions of rows and queries for "events in the last 30 days grouped by hour" take several seconds. Storage costs climb; dashboards feel sluggish. You need a way to keep fine-grained raw data for recent windows while serving fast aggregates for historical windows — without standing up a separate data warehouse.

## Context

- D1 is SQLite-backed and excels at OLTP-style point lookups, but wide aggregate scans over millions of rows are slow.
- A rollup strategy pre-computes sums/counts/averages at coarser time buckets (hourly, daily, weekly) using a cron-triggered Worker.
- Raw rows are retained for a configurable hot window (e.g. 7 days), then deleted after they have been rolled up.
- Query time drops from O(raw rows) to O(rollup buckets) — typically three to four orders of magnitude fewer rows.
- The Cron Trigger fires the rollup Worker; all SQL runs inside D1 batch transactions to stay atomic.

---

## Schema Design

```sql
-- Raw events: high-write, short retention
CREATE TABLE IF NOT EXISTS events_raw (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id  TEXT    NOT NULL,
  metric     TEXT    NOT NULL,  -- e.g. "page_view", "api_call"
  value      REAL    NOT NULL DEFAULT 1,
  ts         INTEGER NOT NULL   -- Unix epoch seconds
);
CREATE INDEX IF NOT EXISTS idx_events_raw_ts ON events_raw (ts);
CREATE INDEX IF NOT EXISTS idx_events_raw_tenant_metric_ts
  ON events_raw (tenant_id, metric, ts);

-- Hourly rollups: computed, long retention
CREATE TABLE IF NOT EXISTS events_rollup_hourly (
  tenant_id  TEXT    NOT NULL,
  metric     TEXT    NOT NULL,
  bucket_ts  INTEGER NOT NULL,  -- Unix epoch of the hour start (ts - ts % 3600)
  total      REAL    NOT NULL DEFAULT 0,
  count      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, metric, bucket_ts)
);

-- Daily rollups: computed from hourly, very long retention
CREATE TABLE IF NOT EXISTS events_rollup_daily (
  tenant_id  TEXT    NOT NULL,
  metric     TEXT    NOT NULL,
  bucket_ts  INTEGER NOT NULL,  -- Unix epoch of the day start (ts - ts % 86400)
  total      REAL    NOT NULL DEFAULT 0,
  count      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, metric, bucket_ts)
);

-- Watermark: tracks the last fully rolled-up timestamp
CREATE TABLE IF NOT EXISTS rollup_watermark (
  id        INTEGER PRIMARY KEY CHECK (id = 1),
  hourly_ts INTEGER NOT NULL DEFAULT 0,
  daily_ts  INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO rollup_watermark (id, hourly_ts, daily_ts) VALUES (1, 0, 0);
```

---

## Cron-Triggered Rollup Worker

```typescript
// src/cron/rollup.ts
export async function runHourlyRollup(db: D1Database): Promise<void> {
  const watermark = await db
    .prepare('SELECT hourly_ts FROM rollup_watermark WHERE id = 1')
    .first<{ hourly_ts: number }>();

  const fromTs = watermark?.hourly_ts ?? 0;
  // Roll up all complete hours before the current one
  const toTs = Math.floor(Date.now() / 1000 / 3600) * 3600;

  if (fromTs >= toTs) return; // Nothing to roll up yet

  // Aggregate raw events into hourly buckets
  const rows = await db
    .prepare(
      `SELECT tenant_id, metric,
              (ts - ts % 3600) AS bucket_ts,
              SUM(value) AS total,
              COUNT(*)   AS count
       FROM events_raw
       WHERE ts >= ? AND ts < ?
       GROUP BY tenant_id, metric, bucket_ts`
    )
    .bind(fromTs, toTs)
    .all<{
      tenant_id: string;
      metric: string;
      bucket_ts: number;
      total: number;
      count: number;
    }>();

  if (!rows.results.length) {
    await db
      .prepare('UPDATE rollup_watermark SET hourly_ts = ? WHERE id = 1')
      .bind(toTs)
      .run();
    return;
  }

  // Upsert rollup rows + advance watermark in a single batch
  const stmts: D1PreparedStatement[] = rows.results.map((r) =>
    db.prepare(
      `INSERT INTO events_rollup_hourly (tenant_id, metric, bucket_ts, total, count)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT (tenant_id, metric, bucket_ts)
       DO UPDATE SET total = total + excluded.total,
                     count = count + excluded.count`
    ).bind(r.tenant_id, r.metric, r.bucket_ts, r.total, r.count)
  );

  stmts.push(
    db
      .prepare('UPDATE rollup_watermark SET hourly_ts = ? WHERE id = 1')
      .bind(toTs)
  );

  await db.batch(stmts);
}
```

---

## Pruning Raw Events After Rollup

```typescript
// src/cron/prune.ts
const RAW_RETENTION_SECONDS = 7 * 24 * 3600; // 7 days

export async function pruneRawEvents(db: D1Database): Promise<number> {
  const cutoff = Math.floor(Date.now() / 1000) - RAW_RETENTION_SECONDS;

  // Only prune rows that have been rolled up (ts < watermark)
  const watermark = await db
    .prepare('SELECT hourly_ts FROM rollup_watermark WHERE id = 1')
    .first<{ hourly_ts: number }>();

  const safeTs = Math.min(cutoff, watermark?.hourly_ts ?? 0);

  const result = await db
    .prepare('DELETE FROM events_raw WHERE ts < ? LIMIT 5000')
    .bind(safeTs)
    .run();

  return result.meta.changes ?? 0;
}
```

---

## Wrangler Cron Configuration

```toml
# wrangler.toml
name = "analytics-worker"
main = "src/index.ts"

[[d1_databases]]
binding = "DB"
database_name = "analytics"
database_id = "<your-database-id>"

[triggers]
crons = ["0 * * * *"]   # Hourly rollup
```

```typescript
// src/index.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    await runHourlyRollup(env.DB);
    const deleted = await pruneRawEvents(env.DB);
    console.log(`Pruned ${deleted} raw event rows`);
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    return handleDashboardQuery(request, env);
  },
};
```

---

## Query Helper — Tiered Read

Serve dashboard queries from rollups for historical data, raw table for the most recent hour.

```typescript
// src/handlers/dashboard.ts
export async function handleDashboardQuery(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const tenantId = url.searchParams.get('tenant') ?? '';
  const metric = url.searchParams.get('metric') ?? 'page_view';
  const fromTs = Number(url.searchParams.get('from') ?? 0);
  const toTs = Number(url.searchParams.get('to') ?? Math.floor(Date.now() / 1000));

  const currentHourStart = Math.floor(Date.now() / 1000 / 3600) * 3600;

  // Historical: read from hourly rollup
  const historical = await env.DB.prepare(
    `SELECT bucket_ts, total, count FROM events_rollup_hourly
     WHERE tenant_id = ? AND metric = ? AND bucket_ts >= ? AND bucket_ts < ?
     ORDER BY bucket_ts ASC`
  )
    .bind(tenantId, metric, fromTs, Math.min(toTs, currentHourStart))
    .all<{ bucket_ts: number; total: number; count: number }>();

  // Recent (current partial hour): read from raw
  const recent = await env.DB.prepare(
    `SELECT (ts - ts % 3600) AS bucket_ts,
            SUM(value) AS total, COUNT(*) AS count
     FROM events_raw
     WHERE tenant_id = ? AND metric = ? AND ts >= ? AND ts < ?
     GROUP BY bucket_ts`
  )
    .bind(tenantId, metric, currentHourStart, toTs)
    .all<{ bucket_ts: number; total: number; count: number }>();

  return Response.json([...historical.results, ...recent.results]);
}
```

---

## Anti-patterns

- **Rolling up without a watermark**: re-aggregating already-included rows double-counts totals. Always track the last processed boundary.
- **Deleting raw rows before rolling up**: data loss is permanent. Always advance the watermark first, prune second.
- **Rolling up the current partial hour**: partial buckets will be re-computed next run, inflating counts. Only include `ts < floor(now / 3600) * 3600`.
- **Large single DELETE without LIMIT**: D1 has a statement timeout; delete in bounded batches (e.g. 5000 rows per cron tick).
- **Running rollup and prune in the same batch statement**: if prune succeeds but rollup fails on retry, data is silently lost. Keep them separate and ordered.

## Gotchas

- D1 `batch()` is atomic per call; if any statement fails the entire batch rolls back — use this to your advantage for watermark advancement.
- The `ON CONFLICT … DO UPDATE` upsert is safe for re-runs: if the cron fires twice for the same hour (e.g. after a Worker restart), the rollup rows are idempotently summed.
- `result.meta.changes` may be `undefined` on older D1 binding versions; fall back to `0`.
- SQLite `ts % 3600` bucket arithmetic is correct only when `ts` is a Unix epoch integer in seconds. Millisecond timestamps need `ts / 1000` first.

## Verification

```bash
# Insert synthetic events spanning three hours
wrangler d1 execute analytics --command \
  "INSERT INTO events_raw (tenant_id, metric, value, ts)
   SELECT 'acme', 'page_view', 1,
          strftime('%s','now') - (abs(random()) % 10800)
   FROM (SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION
         SELECT 4 UNION SELECT 5 UNION SELECT 6)"

# Trigger rollup manually
wrangler d1 execute analytics --file=./migrations/rollup-once.sql

# Confirm rollup rows exist
wrangler d1 execute analytics --command \
  "SELECT bucket_ts, total, count FROM events_rollup_hourly
   WHERE tenant_id='acme' ORDER BY bucket_ts DESC LIMIT 5"
```

## Related

- `event-sourcing-cloudflare-workers-d1.md`
- `materialized-view-d1-workers.md`
- `temporal-pattern-workers-cron-alarms.md`
- `write-behind-cache-kv-d1.md`

## Sources

- Cloudflare D1 docs — Batch statements: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Workers docs — Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- SQLite docs — `ON CONFLICT` clause: https://www.sqlite.org/lang_conflict.html
