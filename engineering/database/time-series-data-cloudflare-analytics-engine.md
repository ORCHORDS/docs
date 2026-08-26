# Time-Series Data and Workers Analytics Engine

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

D1 write throughput hits limits when every user interaction
(view, vote, impression) writes a row. The `events` table
reaches millions of rows within weeks; aggregate queries
(`COUNT(*) GROUP BY hour`) take seconds. KV writes lose
ordering and cannot be aggregated efficiently. Mobile clients
batch events but have no reliable flush endpoint.

## Context

Cloudflare offers three storage primitives relevant to
time-series and event tracking. Choosing the wrong one for
high-volume event data is the root cause of the symptom above.

| Store                     | Best for                          |
|---------------------------|-----------------------------------|
| D1 (SQLite)               | Structured relational data;       |
|                           | low-volume writes (<100/s)        |
| Workers Analytics Engine  | High-volume event streams;        |
| (WAE)                     | columnar aggregation; built-in    |
|                           | time-windowed SQL; 31-day TTL     |
| KV                        | Point lookups by key; no range    |
|                           | queries; no aggregation           |

For an anonymous social app tracking post views, vote counts,
and active users per board, WAE is the correct primitive for
the event stream. D1 stores the pre-aggregated rollups.

## Workers Analytics Engine — Data Model and Write API

WAE uses a write-once columnar model. Each data point is a
`writeDataPoint()` call from a Worker. Points contain:

- `indexes`: up to 20 string dimensions (filterable in SQL)
- `doubles`: up to 20 float64 metrics
- `blobs`: up to 20 string metadata fields (not filterable)

```ts
// wrangler.toml binding:
// [[analytics_engine_datasets]]
// binding = "ANALYTICS"
// dataset  = "events"

interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  DB: D1Database;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { boardId, postId } = await getRouteParams(req);

    // Fire-and-forget — never throws, <1 µs CPU overhead
    env.ANALYTICS.writeDataPoint({
      indexes: [
        boardId,   // index[0] — shard/filter key
        postId,    // index[1]
        'view',    // index[2] — event type
      ],
      doubles: [
        1,         // double[0] — increment by 1
      ],
      blobs: [
        req.cf?.country ?? 'XX', // blob[0] — debug only
      ],
    });

    return new Response('ok');
  },
};
```

`writeDataPoint()` is non-blocking and batched by the runtime
before being flushed to WAE's columnar store.

## Aggregation Queries Over Time Windows

WAE exposes a SQL API via the Cloudflare dashboard and REST
endpoint. WAE SQL uses a ClickHouse-compatible dialect.

```sql
-- Views per post for the past 24 hours, bucketed by hour
SELECT
  index2                    AS post_id,
  SUM(double1)              AS views,
  toStartOfHour(timestamp)  AS hour
FROM   events
WHERE  index1     = 'my-board-id'
  AND  index3     = 'view'
  AND  timestamp >= NOW() - INTERVAL '1' DAY
GROUP  BY post_id, hour
ORDER  BY hour DESC;
```

Available time-bucket functions: `toStartOfHour()`,
`toStartOfDay()`, `toStartOfWeek()`, `dateDiff()`.

The implicit `timestamp` column stores the write time at
one-second granularity; sub-second ordering is not guaranteed.

## TTL-Based Retention and Daily Rollup to D1

WAE retains data for up to 31 days on the standard plan.
A daily Cron Trigger Worker (cron `0 3 * * *`) queries the
WAE SQL REST API for yesterday's totals (`SUM(double1) GROUP
BY index2`) and upserts them into a `daily_post_stats` table
in D1 using `ON CONFLICT DO UPDATE`. This keeps engagement
history beyond WAE's TTL and enables JOINs with post metadata.

## Choosing the Right Store — Decision Tree

1. Queried by primary key, no aggregation? → **KV**
2. High-volume event stream (>100/s) with time-window
   aggregations and a 31-day horizon? → **WAE**
3. Low-volume (<50/s), needs JOINs with relational data,
   or must survive beyond 31 days? → **D1**
4. Pre-computed counter that needs atomic increment? → **D1**
   with `UPDATE stats SET n = n + 1 WHERE post_id = ?`

Running `SELECT COUNT(*) FROM posts WHERE board_id = ?` on
D1 for every feed page load is an anti-pattern once the table
is large. Maintain a `board_stats` table in D1 with
pre-aggregated counters populated by the WAE rollup cron or
incremented atomically on each write.

## Anti-patterns

- **Writing events to D1 at mobile-app volume** — each D1
  write is an HTTP round-trip with serialization overhead;
  WAE writes are in-memory and runtime-batched.
- **Using KV for time-series data** — KV has no range scan or
  aggregation; you would have to maintain every bucket key
  manually and still cannot query across them.
- **Querying WAE on every feed request** — WAE SQL is an
  external HTTP call with latency; cache aggregates in D1
  or KV with a short TTL (1–5 min).
- **Skipping the daily rollup** — WAE data expires at 31 days;
  without a rollup, historical engagement trends are lost.
- **Storing PII in WAE indexes** — WAE data is not subject to
  GDPR deletion workflows; keep indexes pseudonymous (post IDs,
  board IDs) rather than user emails or device IDs.

## Gotchas

- `writeDataPoint()` is rate-limited per dataset per account;
  check WAE limits in the Cloudflare dashboard before
  launching high-traffic features.
- WAE SQL does not support `JOIN`; aggregate in WAE and merge
  with D1 relational data in application code.
- The WAE REST API requires an API token with the "Account
  Analytics Read" permission — separate from the D1 token.
- WAE indexes are case-sensitive strings; normalize to
  lowercase before writing to avoid split metrics (e.g.,
  `'View'` and `'view'` as separate index3 values).
- WAE's columnar store is eventually consistent; very recent
  writes (last 60 s) may not appear in SQL queries yet.

## Verification

```bash
# Query WAE via curl (replace placeholders)
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/ \
${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: text/plain" \
  -d "SELECT COUNT() AS n FROM events LIMIT 1"

# Expected: {"data":[{"n":12345}],"rows":1,...}
```

## Related

- `database/d1-sqlite-query-optimization.md`
- `database/time-series-patterns-timescaledb-influxdb.md`
- `monitoring/cloudflare-analytics-engine.md`
- `cloudflare/workers-cron-triggers.md`
- `mobile/event-tracking-pipeline.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/
  get-started/
- https://developers.cloudflare.com/analytics/analytics-engine/limits/
- https://developers.cloudflare.com/workers/runtime-apis/
  handlers/scheduled/
