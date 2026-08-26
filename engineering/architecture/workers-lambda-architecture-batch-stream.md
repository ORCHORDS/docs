# Lambda Architecture (Batch + Speed Layers) with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need analytics that are both accurate and fresh. A nightly D1 aggregation job produces correct numbers but they are 24 hours stale. A real-time stream gives up-to-the-second figures but may miss late-arriving events or contain double-counts. Users demand dashboards that show yesterday's verified totals plus today's live activity.

## Context

Nathan Marz's Lambda Architecture addresses this by running two parallel pipelines:

- **Batch layer**: processes the complete historical dataset periodically, producing accurate but latent views.
- **Speed layer**: processes only recent data in real-time, filling the latency gap.
- **Serving layer**: merges results from both layers, preferring batch for older windows and speed for the current window.

Cloudflare Workers provide natural primitives for each layer:

| Layer | Cloudflare primitive |
|-------|----------------------|
| Speed layer ingestion | Tail Worker → Analytics Engine |
| Batch layer | Cron Worker + D1 |
| Serving layer | Worker merging AE + D1 query results |

## Solution

### 1. Speed Layer — Tail Worker to Analytics Engine

```typescript
// tail-worker.ts  (set as tail_worker in wrangler.toml)
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    const points: AnalyticsEngineDataPoint[] = events
      .filter((e) => e.outcome === 'ok')
      .flatMap((e) =>
        e.logs
          .filter((l) => l.level === 'log' && (l.message[0] as any)?.type === 'event')
          .map((l) => {
            const ev = l.message[0] as AppEvent;
            return {
              blobs: [ev.userId, ev.eventName, ev.country],
              doubles: [ev.value ?? 1],
              indexes: [ev.tenantId],
            };
          })
      );

    if (points.length > 0) {
      // Bulk write to Analytics Engine (speed layer store)
      env.EVENTS_AE.writeDataPoints(points);
    }
  },
};

interface AppEvent {
  type: 'event';
  userId: string;
  eventName: string;
  country: string;
  tenantId: string;
  value?: number;
}

interface Env {
  EVENTS_AE: AnalyticsEngineDataset;
}
```

```toml
# wrangler.toml (excerpt)
[[tail_consumers]]
service = "tail-worker"

[[analytics_engine_datasets]]
binding = "EVENTS_AE"
dataset = "app_events"
```

### 2. Batch Layer — Nightly D1 Aggregation Cron

```typescript
// batch-worker.ts
export default {
  async scheduled(event: ScheduledEvent, env: BatchEnv, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runBatch(env));
  },

  async fetch(_req: Request, _env: BatchEnv): Promise<Response> {
    return new Response('Batch worker — invoke via cron only', { status: 403 });
  },
};

async function runBatch(env: BatchEnv): Promise<void> {
  const yesterday = new Date();
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  const dateStr = yesterday.toISOString().slice(0, 10); // 'YYYY-MM-DD'

  // Aggregate raw events table into daily_stats
  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO daily_stats (date, tenant_id, event_name, event_count, total_value)
      SELECT
        date(occurred_at) AS date,
        tenant_id,
        event_name,
        COUNT(*)          AS event_count,
        SUM(value)        AS total_value
      FROM raw_events
      WHERE date(occurred_at) = ?
      GROUP BY 1, 2, 3
      ON CONFLICT (date, tenant_id, event_name)
        DO UPDATE SET
          event_count = excluded.event_count,
          total_value = excluded.total_value,
          updated_at  = unixepoch()
    `).bind(dateStr),

    // Mark the window as complete so the serving layer knows to trust it
    env.DB.prepare(`
      INSERT OR REPLACE INTO batch_windows (date, completed_at)
      VALUES (?, unixepoch())
    `).bind(dateStr),
  ]);

  console.log(JSON.stringify({ type: 'event', eventName: 'batch.complete', value: 1,
    userId: 'system', country: 'XX', tenantId: 'system' }));
}

interface BatchEnv {
  DB: D1Database;
}
```

```toml
# wrangler.toml (excerpt)
[triggers]
crons = ["0 3 * * *"]  # 03:00 UTC daily
```

### 3. Serving Layer — Merging Batch and Speed Results

```typescript
// serving-worker.ts
import { Env } from './types';

interface DailyStats {
  date: string;
  eventName: string;
  eventCount: number;
  totalValue: number;
  source: 'batch' | 'speed';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const tenantId = url.searchParams.get('tenantId') ?? '';
    const days = Math.min(30, parseInt(url.searchParams.get('days') ?? '7'));

    if (!tenantId) return new Response('tenantId required', { status: 400 });

    const stats = await queryMerged(env, tenantId, days);
    return Response.json(stats);
  },
};

async function queryMerged(env: Env, tenantId: string, days: number): Promise<DailyStats[]> {
  const cutoff = new Date();
  cutoff.setUTCDate(cutoff.getUTCDate() - days);
  const cutoffStr = cutoff.toISOString().slice(0, 10);

  // 1. Determine which dates have completed batch windows
  const { results: windows } = await env.DB.prepare(
    `SELECT date FROM batch_windows WHERE date >= ? ORDER BY date`
  ).bind(cutoffStr).all<{ date: string }>();

  const batchDates = new Set(windows.map((w) => w.date));

  // 2. Fetch batch layer data for completed windows
  const batchRows: DailyStats[] = [];
  if (batchDates.size > 0) {
    const placeholders = [...batchDates].map(() => '?').join(',');
    const { results } = await env.DB.prepare(
      `SELECT date, event_name, event_count, total_value
       FROM daily_stats
       WHERE tenant_id = ? AND date IN (${placeholders})
       ORDER BY date, event_name`
    ).bind(tenantId, ...[...batchDates]).all<any>();

    batchRows.push(...results.map((r: any) => ({
      date: r.date,
      eventName: r.event_name,
      eventCount: r.event_count,
      totalValue: r.total_value,
      source: 'batch' as const,
    })));
  }

  // 3. Fetch speed layer data for dates without a completed batch window
  // Analytics Engine SQL API — query last 24h for incomplete windows
  const speedRows: DailyStats[] = await querySpeedLayer(env, tenantId, cutoffStr, batchDates);

  // 4. Merge: batch wins for its dates; speed fills the gaps
  const all = [...batchRows, ...speedRows];
  all.sort((a, b) => a.date.localeCompare(b.date) || a.eventName.localeCompare(b.eventName));

  return all;
}

async function querySpeedLayer(
  env: Env,
  tenantId: string,
  since: string,
  excludeDates: Set<string>
): Promise<DailyStats[]> {
  // Analytics Engine SQL API (Workers Analytics Engine)
  const sql = `
    SELECT
      toStartOfDay(timestamp) AS date,
      blob2                   AS event_name,
      SUM(_sample_interval)   AS event_count,
      SUM(double1)            AS total_value
    FROM app_events
    WHERE
      index1 = '${tenantId}'
      AND timestamp >= toDateTime('${since} 00:00:00')
    GROUP BY date, event_name
    ORDER BY date, event_name
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'text/plain',
      },
      body: sql,
    }
  );

  if (!res.ok) throw new Error(`Analytics Engine query failed: ${await res.text()}`);

  const data = await res.json<{ data: any[] }>();

  return data.data
    .filter((row) => !excludeDates.has(row.date.slice(0, 10)))
    .map((row) => ({
      date: row.date.slice(0, 10),
      eventName: row.event_name,
      eventCount: Number(row.event_count),
      totalValue: Number(row.total_value),
      source: 'speed' as const,
    }));
}
```

### 4. D1 Schema

```sql
-- migrations/0001_lambda_arch.sql
CREATE TABLE IF NOT EXISTS raw_events (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  event_name  TEXT NOT NULL,
  user_id     TEXT NOT NULL,
  value       REAL NOT NULL DEFAULT 1,
  occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_raw_events_date    ON raw_events (date(occurred_at));
CREATE INDEX IF NOT EXISTS idx_raw_events_tenant  ON raw_events (tenant_id, date(occurred_at));

CREATE TABLE IF NOT EXISTS daily_stats (
  date        TEXT NOT NULL,
  tenant_id   TEXT NOT NULL,
  event_name  TEXT NOT NULL,
  event_count INTEGER NOT NULL DEFAULT 0,
  total_value REAL    NOT NULL DEFAULT 0,
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (date, tenant_id, event_name)
);

CREATE TABLE IF NOT EXISTS batch_windows (
  date         TEXT PRIMARY KEY,
  completed_at INTEGER NOT NULL DEFAULT (unixepoch())
);
```

## Implementation Details

- **Tail Worker limitations**: Tail Workers receive log data, not raw request/response bodies. Encode event payloads in `console.log()` calls from the primary Worker using a typed schema.
- **Analytics Engine sampling**: AE uses sampling for high-volume datasets. `_sample_interval` compensates for samples — always use `SUM(_sample_interval)` not `COUNT(*)` for event counts.
- **Idempotent batch**: The batch job uses `INSERT ... ON CONFLICT DO UPDATE` so re-running for the same date is safe.
- **batch_windows table**: This is the critical coordination record. The serving layer cannot know which dates are complete without it — do not skip it.
- **Speed layer staleness window**: AE data may lag by up to 60 seconds due to Tail Worker delivery guarantees. Communicate this to frontend consumers.
- **Cron timing**: Run the batch at 03:00 UTC to avoid peak traffic; ensure yesterday's data is fully written before aggregating (add a 30-minute buffer if events can arrive late).

## Anti-patterns

- **Serving from batch only**: Dashboard shows 24-hour-old data. Users lose trust.
- **Serving from speed only**: Double-counts and sampling errors accumulate over time.
- **Re-querying AE for completed windows**: Wasted latency and cost. Once a batch window is complete, always serve from D1.
- **Omitting `batch_windows`**: Without a completion marker, the serving layer cannot distinguish between "batch not run yet" and "no data for that date".
- **Single cron for batch + speed reconciliation**: Reconciliation should be a separate job with different retry logic.

## Gotchas

- Tail Workers share the same CPU limit as the primary Worker. Batch-heavy Tail Worker processing can exceed 50 ms CPU budget and get killed.
- Analytics Engine SQL API is a REST endpoint, not a Worker binding — it requires an API token with `account:read` + `analytics_engine:read` permissions.
- D1 `batch()` limit is 100 statements per call. If aggregating many tenants, paginate.
- The cron Worker has a 30-second wall time limit (Unbound plan: 15 minutes). Large historical re-aggregations must be chunked.
- AE `index1` is limited to 32 bytes. Truncate or hash long tenant IDs.

## Verification

```bash
# Trigger batch job manually
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/batch-worker/schedules" \
  -H "Authorization: Bearer $CF_API_TOKEN"

# Verify D1 daily_stats populated
npx wrangler d1 execute my-db --command \
  "SELECT date, SUM(event_count) FROM daily_stats GROUP BY date ORDER BY date DESC LIMIT 7;"

# Verify batch_windows
npx wrangler d1 execute my-db --command \
  "SELECT date, datetime(completed_at, 'unixepoch') FROM batch_windows ORDER BY date DESC LIMIT 7;"

# Hit serving layer
curl "https://serving-worker.example.workers.dev/?tenantId=tenant-1&days=7" | jq '[.[] | {date,source}] | group_by(.source)'
```

## Related

- `workers-cqrs-command-query-separation.md`
- `repository-pattern-d1.md`
- `workers-graceful-degradation-feature-tiers.md`

## Sources

- Marz, N. & Warren, J. (2015). *Big Data*. Manning.
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Tail Workers: https://developers.cloudflare.com/workers/observability/tail-workers/
- Cloudflare D1: https://developers.cloudflare.com/d1/
