# Streaming D1 Data Exports for Analytics Pipelines

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Operational data in D1 needs to flow into downstream analytics systems—Cloudflare Analytics Engine, BI tools, or data warehouses—without blocking the primary Worker serving user traffic. SQLite's single-writer model and D1's query size limits make naive full-table dumps impractical for large datasets. A robust pipeline streams data in pages, checkpoints progress to R2, and feeds aggregations to Analytics Engine on a schedule rather than polling in the hot path.

## Context

D1 does not offer native change data capture (CDC) or WAL-based replication to external systems. Analytics pipelines must therefore be built on three primitives: (1) cursor-based incremental exports using monotonic `rowid` or `updated_at` columns, (2) the D1 REST API for bulk read access outside of Worker bindings, and (3) R2 as a staging area for raw export files before they are consumed by downstream tools. Cloudflare Analytics Engine provides a lightweight columnar store designed to ingest high-cardinality events from Workers at low cost, making it the natural landing zone for D1 aggregations pushed on a schedule.

## Cursor-Based Incremental Export to R2

The export Worker runs on a Cron Trigger, reads a checkpoint from R2, pages through D1 in batches of 1,000 rows, serialises each page as newline-delimited JSON, and writes partitioned objects to R2.

```typescript
// src/export-worker.ts
import { Env } from './types';

const PAGE_SIZE = 1_000;
const CHECKPOINT_KEY = 'exports/checkpoints/d1-orders.json';

interface Checkpoint {
  lastRowId: number;
  exportedAt: string;
}

interface OrderRow {
  rowid: number;
  id: string;
  user_id: string;
  total_cents: number;
  status: string;
  created_at: number;
}

export async function runExport(env: Env): Promise<void> {
  // 1. Load checkpoint — default to 0 (full export) on first run.
  let lastRowId = 0;
  const checkpointObj = await env.EXPORT_BUCKET.get(CHECKPOINT_KEY);
  if (checkpointObj) {
    const cp = (await checkpointObj.json()) as Checkpoint;
    lastRowId = cp.lastRowId;
  }

  let page = 0;
  let totalRows = 0;

  while (true) {
    // 2. Fetch a page of rows newer than the checkpoint.
    const { results } = await env.DB.prepare(
      `SELECT rowid, id, user_id, total_cents, status, created_at
       FROM orders
       WHERE rowid > ?
       ORDER BY rowid ASC
       LIMIT ?`,
    )
      .bind(lastRowId, PAGE_SIZE)
      .all<OrderRow>();

    if (results.length === 0) break;

    // 3. Serialise as NDJSON and write to R2 with a date-partitioned key.
    const date = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
    const key = `exports/orders/dt=${date}/page-${String(page).padStart(6, '0')}.ndjson`;
    const body = results.map(r => JSON.stringify(r)).join('\n');

    await env.EXPORT_BUCKET.put(key, body, {
      httpMetadata: { contentType: 'application/x-ndjson' },
      customMetadata: {
        exportedAt: new Date().toISOString(),
        rowCount: String(results.length),
        minRowId: String(results[0].rowid),
        maxRowId: String(results[results.length - 1].rowid),
      },
    });

    lastRowId = results[results.length - 1].rowid;
    totalRows += results.length;
    page++;

    console.log(`Exported page ${page}: ${results.length} rows, lastRowId=${lastRowId}`);

    // 4. If we got fewer rows than PAGE_SIZE we have reached the tail.
    if (results.length < PAGE_SIZE) break;
  }

  // 5. Persist checkpoint.
  await env.EXPORT_BUCKET.put(
    CHECKPOINT_KEY,
    JSON.stringify({ lastRowId, exportedAt: new Date().toISOString() } satisfies Checkpoint),
    { httpMetadata: { contentType: 'application/json' } },
  );

  console.log(`Export complete: ${totalRows} rows across ${page} pages.`);
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runExport(env));
  },
};
```

## Feeding Analytics Engine from D1 Aggregations

Push pre-aggregated metrics to Analytics Engine rather than raw rows to stay within the 25 blobs + 20 doubles per event limit and to keep Analytics Engine query costs low.

```typescript
// src/analytics-push.ts
import { Env } from './types';

interface HourlyStats {
  hour_bucket: number;  // Unix timestamp truncated to the hour.
  status: string;
  order_count: number;
  revenue_cents: number;
  avg_order_cents: number;
}

export async function pushHourlyAggregates(env: Env): Promise<void> {
  // Compute aggregates for the previous complete hour.
  const nowSec = Math.floor(Date.now() / 1000);
  const hourStart = nowSec - (nowSec % 3600) - 3600; // previous hour
  const hourEnd = hourStart + 3600;

  const { results } = await env.DB.prepare(
    `SELECT
       ? AS hour_bucket,
       status,
       COUNT(*)              AS order_count,
       SUM(total_cents)      AS revenue_cents,
       AVG(total_cents)      AS avg_order_cents
     FROM orders
     WHERE created_at >= ? AND created_at < ?
     GROUP BY status`,
  )
    .bind(hourStart, hourStart, hourEnd)
    .all<HourlyStats>();

  for (const row of results) {
    // Analytics Engine writeDataPoint: up to 25 blobs, 20 doubles, 1 index.
    env.ANALYTICS.writeDataPoint({
      blobs: [row.status],            // blob1 = order status
      doubles: [
        row.order_count,              // double1 = count
        row.revenue_cents,            // double2 = revenue
        row.avg_order_cents,          // double3 = avg order value
      ],
      indexes: [String(hourStart)],   // index1 = hour bucket (for time-series queries)
    });
  }

  console.log(`Pushed ${results.length} aggregate rows for hour ${new Date(hourStart * 1000).toISOString()}`);
}
```

## CDC-Like Patterns with D1 Triggers and an Outbox Table

SQLite triggers can populate an outbox table on every INSERT/UPDATE/DELETE, giving a lightweight CDC foundation without external tooling.

```sql
-- Migration: create the outbox table and triggers.
CREATE TABLE IF NOT EXISTS outbox (
  rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name  TEXT    NOT NULL,
  operation   TEXT    NOT NULL CHECK(operation IN ('INSERT', 'UPDATE', 'DELETE')),
  row_id      TEXT    NOT NULL,
  payload     TEXT    NOT NULL,  -- JSON snapshot of the affected row.
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  processed   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_outbox_unprocessed
  ON outbox(processed, created_at) WHERE processed = 0;

-- Trigger: capture inserts on the orders table.
CREATE TRIGGER IF NOT EXISTS orders_after_insert
AFTER INSERT ON orders
BEGIN
  INSERT INTO outbox (table_name, operation, row_id, payload)
  VALUES (
    'orders',
    'INSERT',
    NEW.id,
    json_object(
      'id',          NEW.id,
      'user_id',     NEW.user_id,
      'total_cents', NEW.total_cents,
      'status',      NEW.status,
      'created_at',  NEW.created_at
    )
  );
END;

-- Trigger: capture status updates.
CREATE TRIGGER IF NOT EXISTS orders_after_update_status
AFTER UPDATE OF status ON orders
BEGIN
  INSERT INTO outbox (table_name, operation, row_id, payload)
  VALUES (
    'orders',
    'UPDATE',
    NEW.id,
    json_object(
      'id',          NEW.id,
      'status',      NEW.status,
      'prev_status', OLD.status,
      'updated_at',  unixepoch()
    )
  );
END;
```

```typescript
// Drain the outbox and forward events to a Queue for downstream processing.
export async function drainOutbox(env: Env): Promise<void> {
  const BATCH = 500;

  while (true) {
    const { results } = await env.DB.prepare(
      `SELECT rowid, table_name, operation, row_id, payload
       FROM outbox
       WHERE processed = 0
       ORDER BY rowid ASC
       LIMIT ?`,
    )
      .bind(BATCH)
      .all<{ rowid: number; table_name: string; operation: string; row_id: string; payload: string }>();

    if (results.length === 0) break;

    // Send to a Cloudflare Queue for fan-out to downstream consumers.
    await env.CDC_QUEUE.sendBatch(
      results.map(r => ({
        body: { table: r.table_name, op: r.operation, id: r.row_id, data: JSON.parse(r.payload) },
      })),
    );

    // Mark as processed in a single batch update.
    const ids = results.map(r => r.rowid);
    await env.DB.prepare(
      `UPDATE outbox SET processed = 1 WHERE rowid IN (${ids.map(() => '?').join(',')})`,
    )
      .bind(...ids)
      .run();

    if (results.length < BATCH) break;
  }
}
```

## Anti-patterns

- Using `OFFSET`-based pagination for exports — `OFFSET N` causes a full-scan of the leading N rows on each page. Always use `WHERE rowid > ?` cursor pagination for large exports.
- Exporting within a user-facing Worker request — D1 query execution time contributes to the Worker CPU time limit (50 ms on free, 30 s on paid). Move bulk exports to Cron Triggers or Queue consumers.
- Writing one R2 object per row — R2 object creation has a per-request overhead; batch rows into multi-megabyte NDJSON files to amortise the cost.
- Parsing and re-serialising Analytics Engine blobs as JSON strings — blobs are limited to 1,000 bytes each; store only discriminating categorical values, not full JSON payloads.

## Gotchas

- D1's REST API returns query results as JSON arrays; very large rows (e.g. `TEXT` columns storing base64 images) can cause the response to exceed the 100 MB REST response limit. Exclude large columns from export queries and fetch them separately if needed.
- SQLite triggers fire synchronously within the transaction; if trigger logic fails (e.g. `outbox` is full or the JSON exceeds column limits), the parent INSERT/UPDATE rolls back too. Keep trigger bodies minimal and the `outbox` table unbounded in size.
- Analytics Engine `writeDataPoint` is fire-and-forget with no acknowledgement. If the Worker is evicted before the event is flushed, the data point is silently dropped. Use the outbox pattern (write to D1 first, then enqueue) for durable event delivery.

## Verification

```bash
# Check unprocessed outbox depth.
wrangler d1 execute <DB_NAME> \
  --command "SELECT COUNT(*) AS pending FROM outbox WHERE processed = 0;"

# List recent R2 export objects.
wrangler r2 object list <BUCKET_NAME> --prefix "exports/orders/"

# Tail Cron Trigger logs for the export Worker.
wrangler tail <WORKER_NAME> --format pretty

# Query Analytics Engine for last-hour order revenue (via the CF dashboard GraphQL API).
# Use: https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql
# SQL: SELECT blob1 AS status, SUM(_sample_interval * double2) AS revenue
#      FROM <DATASET> WHERE timestamp > now() - INTERVAL '1' HOUR GROUP BY blob1;
```

## Related

- `database/d1-batch-operations-performance.md`
- `database/d1-triggers-computed-columns.md`
- `database/time-series-data-cloudflare-analytics-engine.md`
- `database/database-change-data-capture.md`

## Sources

- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
