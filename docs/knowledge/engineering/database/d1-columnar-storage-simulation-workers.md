# D1 Columnar Storage Simulation Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need OLAP-style analytics on a D1 database — summing millions of event rows,
computing per-dimension aggregates, or running funnel queries — but D1 uses SQLite's
row-oriented storage which reads every column of a row even when your query touches
only one or two.  Full table scans on wide event tables are slow and consume quota.
You want columnar-style read performance without migrating to a dedicated analytics
store like ClickHouse or Cloudflare Analytics Engine.

---

## Context

Columnar databases (ClickHouse, DuckDB, Parquet files) store each column in its own
contiguous segment so aggregate queries read only the columns they need, compress
well, and benefit from SIMD vectorisation.  SQLite stores entire rows together, which
means a `SELECT SUM(revenue) FROM events` still deserves to page in every row's
`user_id`, `session_id`, `metadata` JSON, etc.

The simulation technique is to decompose wide event rows into a set of narrow
vertical tables — one column-family table per frequently-aggregated metric — and write
to all of them together in a batch.  Reads against the narrow tables hit far fewer
pages and compress better in SQLite's B-tree.  A summary/rollup table maintained by a
Cron Trigger brings pre-aggregated results to near-instant latency.

---

## Schema: wide source table vs. narrow column tables

```sql
-- migrations/0020_columnar_sim.sql

-- Source table kept lean; only lookup columns plus a surrogate key.
CREATE TABLE IF NOT EXISTS events (
  event_id    TEXT    PRIMARY KEY,
  user_id     TEXT    NOT NULL,
  occurred_at INTEGER NOT NULL,   -- unixepoch()
  event_type  TEXT    NOT NULL
) STRICT;

CREATE INDEX idx_events_user   ON events (user_id, occurred_at);
CREATE INDEX idx_events_type   ON events (event_type, occurred_at);

-- "Column" tables — each stores one metric per event.
CREATE TABLE IF NOT EXISTS ev_revenue (
  event_id TEXT    NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  value    REAL    NOT NULL
) STRICT;
CREATE INDEX idx_ev_revenue_event ON ev_revenue (event_id);

CREATE TABLE IF NOT EXISTS ev_duration_ms (
  event_id TEXT    NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  value    INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS ev_item_count (
  event_id TEXT    NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  value    INTEGER NOT NULL
) STRICT;

-- Pre-aggregated daily rollup — materialised on demand.
CREATE TABLE IF NOT EXISTS daily_rollup (
  day         TEXT  NOT NULL,           -- 'YYYY-MM-DD'
  event_type  TEXT  NOT NULL,
  total_revenue   REAL    NOT NULL DEFAULT 0,
  total_duration  INTEGER NOT NULL DEFAULT 0,
  event_count     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, event_type)
) STRICT;
```

---

## Writing events: atomic batch insert across column tables

```typescript
// src/lib/event-writer.ts
import type { D1Database } from '@cloudflare/workers-types';
import { randomUUID } from 'node:crypto';   // available in Workers

export interface EventPayload {
  user_id: string;
  event_type: string;
  occurred_at?: number;
  revenue?: number;
  duration_ms?: number;
  item_count?: number;
}

export async function insertEvent(
  db: D1Database,
  payload: EventPayload,
): Promise<string> {
  const eventId = randomUUID();
  const ts = payload.occurred_at ?? Math.floor(Date.now() / 1000);

  const stmts = [
    db
      .prepare(
        `INSERT INTO events (event_id, user_id, occurred_at, event_type)
         VALUES (?1, ?2, ?3, ?4)`,
      )
      .bind(eventId, payload.user_id, ts, payload.event_type),
  ];

  if (payload.revenue !== undefined) {
    stmts.push(
      db
        .prepare(`INSERT INTO ev_revenue (event_id, value) VALUES (?1, ?2)`)
        .bind(eventId, payload.revenue),
    );
  }
  if (payload.duration_ms !== undefined) {
    stmts.push(
      db
        .prepare(`INSERT INTO ev_duration_ms (event_id, value) VALUES (?1, ?2)`)
        .bind(eventId, payload.duration_ms),
    );
  }
  if (payload.item_count !== undefined) {
    stmts.push(
      db
        .prepare(`INSERT INTO ev_item_count (event_id, value) VALUES (?1, ?2)`)
        .bind(eventId, payload.item_count),
    );
  }

  await db.batch(stmts);
  return eventId;
}
```

---

## Aggregate query — touch only the narrow column table

```typescript
// src/lib/analytics.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface RevenueByType {
  event_type: string;
  total_revenue: number;
  event_count: number;
}

/**
 * Aggregates revenue per event_type for a date range.
 * Only scans ev_revenue + a covering index on events — never touches
 * ev_duration_ms or ev_item_count.
 */
export async function revenueByType(
  db: D1Database,
  fromUnix: number,
  toUnix: number,
): Promise<RevenueByType[]> {
  const { results } = await db
    .prepare(
      `SELECT e.event_type,
              SUM(r.value)  AS total_revenue,
              COUNT(*)      AS event_count
       FROM   ev_revenue r
       JOIN   events e USING (event_id)
       WHERE  e.occurred_at BETWEEN ?1 AND ?2
       GROUP  BY e.event_type
       ORDER  BY total_revenue DESC`,
    )
    .bind(fromUnix, toUnix)
    .all<RevenueByType>();

  return results;
}
```

---

## Rollup maintenance via Cron Trigger

```typescript
// src/cron/rollup.ts
import type { D1Database } from '@cloudflare/workers-types';

/**
 * Called from the Worker's scheduled() handler.
 * Upserts yesterday's aggregate into daily_rollup.
 */
export async function refreshDailyRollup(db: D1Database): Promise<void> {
  await db
    .prepare(
      `INSERT INTO daily_rollup (day, event_type, total_revenue, total_duration, event_count)
       SELECT
         date(e.occurred_at, 'unixepoch')   AS day,
         e.event_type,
         COALESCE(SUM(r.value),  0)         AS total_revenue,
         COALESCE(SUM(d.value),  0)         AS total_duration,
         COUNT(DISTINCT e.event_id)         AS event_count
       FROM   events e
       LEFT JOIN ev_revenue     r USING (event_id)
       LEFT JOIN ev_duration_ms d USING (event_id)
       WHERE  date(e.occurred_at, 'unixepoch') = date('now', '-1 day')
       GROUP  BY day, e.event_type
       ON CONFLICT (day, event_type) DO UPDATE SET
         total_revenue  = excluded.total_revenue,
         total_duration = excluded.total_duration,
         event_count    = excluded.event_count`,
    )
    .run();
}

// wrangler.toml
// [[triggers.crons]]
// crons = ["5 0 * * *"]    -- 00:05 UTC every day
```

---

## Serving pre-aggregated results

```typescript
// src/handlers/analytics-handler.ts
import type { D1Database } from '@cloudflare/workers-types';

export async function getDailyRollup(
  db: D1Database,
  day: string,    // 'YYYY-MM-DD'
): Promise<unknown[]> {
  const { results } = await db
    .prepare(
      `SELECT event_type, total_revenue, total_duration, event_count
       FROM   daily_rollup
       WHERE  day = ?1
       ORDER  BY total_revenue DESC`,
    )
    .bind(day)
    .all();
  return results;
}
```

---

## Compression via integer encoding

SQLite stores `INTEGER` values in 1–8 bytes depending on magnitude.  If you quantise
`REAL` metrics to integer units (e.g. store revenue in cents rather than dollars) you
both save space and eliminate floating-point rounding:

```sql
-- Store revenue as integer cents.
CREATE TABLE IF NOT EXISTS ev_revenue_cents (
  event_id TEXT    NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  value    INTEGER NOT NULL   -- cents, e.g. 1995 = $19.95
) STRICT;
```

```typescript
// Convert at the boundary.
const revenueCents = Math.round(payload.revenue * 100);
stmts.push(db.prepare('INSERT INTO ev_revenue_cents VALUES (?1, ?2)')
  .bind(eventId, revenueCents));
```

---

## Anti-patterns

- **Joining all column tables in every query** — the whole point is to read only the
  columns a given query needs.  A join that brings in all column tables is no better
  than a wide row table; it is worse due to join overhead.

- **Skipping the rollup table** — running `SUM()` over raw column tables on every
  dashboard request exhausts D1 row-scan budget quickly.  Pre-aggregate into
  `daily_rollup` and serve cold reads from there.

- **Referencing source columns via SELECT \*** — always project explicit columns when
  querying the narrow tables to avoid accidental column bloat as the schema grows.

- **Inconsistent writes** — inserting into `events` but forgetting a `ev_*` insert
  leaves orphaned stubs.  Use `db.batch()` so all inserts succeed or fail atomically.

---

## Gotchas

- `ON DELETE CASCADE` on the `ev_*` tables only fires when `PRAGMA foreign_keys = ON`
  is active for that connection.  D1 enables foreign keys by default; confirm with
  `PRAGMA foreign_keys` if deletes do not cascade.

- SQLite does not parallelise `JOIN` scans.  A query joining 4 column tables still
  runs sequentially.  For more than ~5 million rows, offload heavy aggregations to
  Cloudflare Analytics Engine or stream the data to ClickHouse via a Queue consumer.

- The `daily_rollup` cron may double-count if triggered twice for the same day.  The
  `ON CONFLICT DO UPDATE` upsert is idempotent, so re-running is safe as long as the
  source data has not changed.

- Column tables grow unboundedly.  Pair them with a TTL delete job that prunes raw
  events and cascades through column tables after the rollup window has passed.

---

## Verification

```typescript
// Integration test
import { describe, it, expect, beforeAll } from 'vitest';
import { env } from 'cloudflare:test';
import { insertEvent } from '../src/lib/event-writer';
import { revenueByType } from '../src/lib/analytics';

describe('columnar simulation', () => {
  beforeAll(async () => { /* apply migrations via env.DB.exec */ });

  it('aggregates revenue from narrow column table', async () => {
    const now = Math.floor(Date.now() / 1000);
    await insertEvent(env.DB, { user_id: 'u1', event_type: 'purchase', occurred_at: now, revenue: 19.99 });
    await insertEvent(env.DB, { user_id: 'u2', event_type: 'purchase', occurred_at: now, revenue: 5.00  });
    await insertEvent(env.DB, { user_id: 'u3', event_type: 'view',     occurred_at: now });

    const rows = await revenueByType(env.DB, now - 60, now + 60);
    const purchase = rows.find(r => r.event_type === 'purchase');
    expect(purchase?.total_revenue).toBeCloseTo(24.99, 1);
    expect(purchase?.event_count).toBe(2);
  });
});
```

---

## Related

- `d1-aggregate-filter-pivot-analytics-workers.md` — FILTER clause pivots on standard
  wide tables.
- `d1-materialized-view-simulation-cron.md` — pre-computing aggregates via Cron.
- `d1-window-functions-analytics.md` — running totals and ranks over event streams.
- `time-series-data-cloudflare-analytics-engine.md` — when data volume exceeds what
  D1 can handle, push to Analytics Engine instead.

---

## Sources

- SQLite storage classes and page layout: https://www.sqlite.org/fileformat2.html
- Cloudflare D1 batch operations: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- DuckDB columnar storage explainer (for conceptual comparison): https://duckdb.org/why_duckdb#columnar-vectorized-query-execution-engine
