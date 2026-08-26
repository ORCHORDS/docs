# D1 Archive Table Partitioning Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 table accumulates millions of rows over time — event logs, job history, audit trails, messages. Queries on recent data slow down because the planner scans or sorts across the entire table. `VACUUM` cycles grow longer. The active dataset that workers actually query is 2–5% of total row count. You need to keep old data accessible but move it out of the hot query path without changing the Worker's query interface.

## Context

D1/SQLite has no native table partitioning. The idiomatic pattern is **manual hot/cold table splitting**: write new rows to a small `_hot` table; a scheduled cron Worker moves rows older than a retention window to an `_archive` table; queries against the active dataset stay fast because they only touch `_hot`. For cross-period queries, use `UNION ALL` across both tables or a D1 `ATTACH` join. A `view` unifies both tables behind a single name so application queries need not change.

## Schema

```sql
-- Hot table: recent rows only (e.g. last 30 days)
CREATE TABLE events_hot (
  id          TEXT    PRIMARY KEY,
  user_id     TEXT    NOT NULL,
  event_type  TEXT    NOT NULL,
  payload     TEXT,
  occurred_at TEXT    NOT NULL   -- ISO-8601
);
CREATE INDEX idx_events_hot_user_occurred ON events_hot(user_id, occurred_at DESC);

-- Archive table: same columns, append-only
CREATE TABLE events_archive (
  id          TEXT    PRIMARY KEY,
  user_id     TEXT    NOT NULL,
  event_type  TEXT    NOT NULL,
  payload     TEXT,
  occurred_at TEXT    NOT NULL
);
CREATE INDEX idx_events_archive_user_occurred ON events_archive(user_id, occurred_at DESC);

-- Unified view for full-history queries
CREATE VIEW events AS
  SELECT *, 'hot' AS _source FROM events_hot
  UNION ALL
  SELECT *, 'archive' AS _source FROM events_archive;
```

## Writing New Events (Always to Hot)

```typescript
// src/events.ts
interface Env { DB: D1Database }

export async function recordEvent(
  env: Env,
  id: string,
  userId: string,
  eventType: string,
  payload: unknown
): Promise<void> {
  await env.DB
    .prepare(`
      INSERT INTO events_hot (id, user_id, event_type, payload, occurred_at)
      VALUES (?, ?, ?, ?, ?)
    `)
    .bind(id, userId, eventType, JSON.stringify(payload), new Date().toISOString())
    .run();
}
```

## Archival Cron Worker

```typescript
// src/workers/archive-cron.ts
// wrangler.toml: [triggers] crons = ["0 3 * * *"]   (runs 03:00 UTC daily)

const HOT_RETENTION_DAYS = 30;

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = new Date();
    cutoff.setUTCDate(cutoff.getUTCDate() - HOT_RETENTION_DAYS);
    const cutoffIso = cutoff.toISOString();

    let archived = 0;
    const BATCH = 500;

    while (true) {
      // Read a batch of old rows
      const { results } = await env.DB
        .prepare(`
          SELECT id, user_id, event_type, payload, occurred_at
          FROM events_hot
          WHERE occurred_at < ?
          ORDER BY occurred_at ASC
          LIMIT ?
        `)
        .bind(cutoffIso, BATCH)
        .all<{
          id: string; user_id: string; event_type: string;
          payload: string; occurred_at: string;
        }>();

      if (results.length === 0) break;

      // Insert into archive, then delete from hot — atomic per batch
      const inserts = results.map((r) =>
        env.DB.prepare(`
          INSERT OR IGNORE INTO events_archive
            (id, user_id, event_type, payload, occurred_at)
          VALUES (?, ?, ?, ?, ?)
        `).bind(r.id, r.user_id, r.event_type, r.payload, r.occurred_at)
      );
      const ids = results.map((r) => r.id);
      const placeholders = ids.map(() => '?').join(', ');
      const deleteStmt = env.DB
        .prepare(`DELETE FROM events_hot WHERE id IN (${placeholders})`)
        .bind(...ids);

      await env.DB.batch([...inserts, deleteStmt]);
      archived += results.length;

      // D1 CPU time limit: yield between large batches
      if (results.length < BATCH) break;
    }

    console.log(`Archived ${archived} events older than ${cutoffIso}`);
  },
};
```

## Querying Hot Data Only (Default Path)

```typescript
// Fast — touches only events_hot, which stays small
export async function getRecentUserEvents(
  env: Env,
  userId: string,
  limit = 50
): Promise<EventRow[]> {
  const { results } = await env.DB
    .prepare(`
      SELECT id, event_type, payload, occurred_at
      FROM events_hot
      WHERE user_id = ?
      ORDER BY occurred_at DESC
      LIMIT ?
    `)
    .bind(userId, limit)
    .all<EventRow>();
  return results;
}
```

## Full-History Query via the View

```typescript
// Slower — hits UNION ALL across both tables; use sparingly for audit/export paths
export async function getFullUserHistory(
  env: Env,
  userId: string,
  from: string,
  to: string
): Promise<EventRow[]> {
  const { results } = await env.DB
    .prepare(`
      SELECT id, event_type, payload, occurred_at
      FROM events          -- unified view
      WHERE user_id     = ?
        AND occurred_at >= ?
        AND occurred_at <= ?
      ORDER BY occurred_at DESC
      LIMIT 1000
    `)
    .bind(userId, from, to)
    .all<EventRow>();
  return results;
}
```

## Monitoring Table Sizes in CI / Health Endpoint

```typescript
export async function tableStats(env: Env): Promise<Record<string, number>> {
  const tables = ['events_hot', 'events_archive'];
  const stmts = tables.map((t) =>
    env.DB.prepare(`SELECT COUNT(*) AS cnt FROM ${t}`)
  );
  const results = await env.DB.batch<{ cnt: number }>(stmts);
  return Object.fromEntries(
    tables.map((t, i) => [t, results[i].results[0]?.cnt ?? 0])
  );
}
```

## Anti-patterns

- **Moving rows one by one**: each `DELETE`/`INSERT` is a separate write. Batch 500–1000 rows per `db.batch()` call to stay within D1's per-request row-write limits and avoid CPU timeouts.
- **Using a `date` column with text prefix patterns for range scans**: store timestamps as ISO-8601 (`YYYY-MM-DDTHH:mm:ss.sssZ`) so lexicographic and temporal ordering coincide, enabling index range scans.
- **Querying the view by default in hot paths**: the `UNION ALL` view always reads both tables. Use the direct `events_hot` table in latency-critical paths.
- **Archiving during peak traffic**: run the cron during off-peak UTC hours. The batch `DELETE` takes a brief write lock on `events_hot`.

## Gotchas

- D1 Cron Workers have a **CPU time limit** (typically 30 s for paid plans). Keep individual `db.batch()` calls under ~500 rows and loop until the batch is empty.
- `INSERT OR IGNORE` in the archive inserts is intentional: if the cron crashes mid-batch, a re-run will skip already-archived rows and continue.
- The unified `VIEW` works inside a single D1 database. If you need to query across two separate D1 databases (separate instances), use `ATTACH` with the D1 Sessions API or merge at the Worker layer.
- Deleting in a batch that includes both the insert and the delete statements ensures the two tables never diverge on a partial failure — D1 `batch()` is transactional.

## Verification

```typescript
// Insert 3 old events and 1 recent, run archival, verify counts
const old = new Date();
old.setUTCDate(old.getUTCDate() - 60);
await env.DB.batch([
  env.DB.prepare("INSERT INTO events_hot VALUES ('e1','u1','click','{}',?)").bind(old.toISOString()),
  env.DB.prepare("INSERT INTO events_hot VALUES ('e2','u1','view','{}',?)").bind(old.toISOString()),
  env.DB.prepare("INSERT INTO events_hot VALUES ('e3','u1','buy','{}',?)").bind(old.toISOString()),
  env.DB.prepare("INSERT INTO events_hot VALUES ('e4','u1','login','{}',?)").bind(new Date().toISOString()),
]);

await archiveCron(env);   // call the scheduled handler directly in tests

const stats = await tableStats(env);
console.assert(stats.events_hot === 1, 'only the recent event stays in hot');
console.assert(stats.events_archive === 3, '3 old events in archive');
```

## Related

- `d1-hot-cold-data-tiering.md`
- `d1-time-series-partitioning.md`
- `d1-vacuum-incremental-maintenance-workers.md`
- `d1-batch-operations-performance.md`

## Sources

- D1 Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite CREATE VIEW: https://www.sqlite.org/lang_createview.html
