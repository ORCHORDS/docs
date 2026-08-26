# Cloudflare GraphQL API Metrics Export to D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need more than 90 days of Cloudflare platform metrics (zone HTTP analytics,
Workers invocations, cache ratios, firewall events) for capacity planning,
long-term SLO reporting, or cost attribution — but the Cloudflare dashboard retains
GraphQL Analytics data for only 90 days and provides no native export mechanism.

## Context

Cloudflare exposes platform-level metrics through a GraphQL Analytics API at
`https://api.cloudflare.com/client/v4/graphql`. This is distinct from Analytics
Engine's SQL API: GraphQL Analytics covers Cloudflare's own infrastructure signals
(HTTP requests, cache, Workers metrics, Firewall); Analytics Engine is for
user-written `writeDataPoint` events. A scheduled Worker running on a cron trigger
can pull the previous hour's aggregates from the GraphQL API and INSERT them into D1
for indefinite retention. Because the API supports hourly granularity, each cron
run backfills exactly one row per dimension per metric type, keeping D1 row counts
manageable. The existing `analytics-engine-graphql-api-time-series-dashboard.md`
article covers querying this API for live dashboards; this article covers the D1
export pipeline for historical retention.

---

## D1 schema

```sql
-- migrations/0001_graphql_metrics.sql
CREATE TABLE IF NOT EXISTS cf_zone_hourly (
  zone_id       TEXT    NOT NULL,
  hour_utc      TEXT    NOT NULL,   -- ISO-8601 truncated to hour: '2026-08-23T14:00:00Z'
  requests      INTEGER NOT NULL DEFAULT 0,
  bytes         INTEGER NOT NULL DEFAULT 0,
  cache_hits    INTEGER NOT NULL DEFAULT 0,
  cache_misses  INTEGER NOT NULL DEFAULT 0,
  errors_4xx    INTEGER NOT NULL DEFAULT 0,
  errors_5xx    INTEGER NOT NULL DEFAULT 0,
  inserted_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (zone_id, hour_utc)
);

CREATE TABLE IF NOT EXISTS cf_workers_hourly (
  worker_name   TEXT    NOT NULL,
  hour_utc      TEXT    NOT NULL,
  invocations   INTEGER NOT NULL DEFAULT 0,
  errors        INTEGER NOT NULL DEFAULT 0,
  cpu_time_p50  REAL,
  cpu_time_p99  REAL,
  inserted_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (worker_name, hour_utc)
);
```

Upsert on `(zone_id, hour_utc)` makes the cron idempotent — re-runs after failure
do not create duplicate rows.

## GraphQL query construction

```typescript
// src/graphql-fetch.ts
interface ZoneHourlyRow {
  requests: number;
  bytes: number;
  cachedRequests: number;
  status4xx: number;
  status5xx: number;
}

export async function fetchZoneHourly(
  zoneId: string,
  hour: Date,
  apiToken: string
): Promise<ZoneHourlyRow> {
  const since = hour.toISOString();
  const until = new Date(hour.getTime() + 3_600_000).toISOString();

  const query = `
    query ZoneHourly($zoneTag: String!, $since: String!, $until: String!) {
      viewer {
        zones(filter: { zoneTag: $zoneTag }) {
          httpRequests1hGroups(
            limit: 1
            filter: { datetime_geq: $since, datetime_lt: $until }
          ) {
            sum {
              requests
              bytes
              cachedRequests
              responseStatusMap { edgeResponseStatus value }
            }
          }
        }
      }
    }
  `;

  const res = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables: { zoneTag: zoneId, since, until } }),
  });

  const json = await res.json<{ data: { viewer: { zones: Array<{ httpRequests1hGroups: Array<{ sum: any }> }> } } }>();
  const sum = json.data.viewer.zones[0]?.httpRequests1hGroups[0]?.sum;
  if (!sum) return { requests: 0, bytes: 0, cachedRequests: 0, status4xx: 0, status5xx: 0 };

  const status4xx = (sum.responseStatusMap ?? [])
    .filter((s: { edgeResponseStatus: number }) => s.edgeResponseStatus >= 400 && s.edgeResponseStatus < 500)
    .reduce((acc: number, s: { value: number }) => acc + s.value, 0);
  const status5xx = (sum.responseStatusMap ?? [])
    .filter((s: { edgeResponseStatus: number }) => s.edgeResponseStatus >= 500)
    .reduce((acc: number, s: { value: number }) => acc + s.value, 0);

  return { requests: sum.requests, bytes: sum.bytes, cachedRequests: sum.cachedRequests, status4xx, status5xx };
}
```

## Scheduled Worker — cron export pipeline

```typescript
// src/index.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    // Export the hour that ended one hour ago (fully closed window)
    const now = new Date();
    const prevHour = new Date(now);
    prevHour.setUTCMinutes(0, 0, 0);
    prevHour.setUTCHours(prevHour.getUTCHours() - 1);
    const hourStr = prevHour.toISOString().replace(/:\d{2}\.\d{3}Z$/, ":00:00Z");

    for (const zoneId of env.ZONE_IDS.split(",")) {
      const row = await fetchZoneHourly(zoneId, prevHour, env.CF_API_TOKEN);

      await env.DB.prepare(`
        INSERT INTO cf_zone_hourly
          (zone_id, hour_utc, requests, bytes, cache_hits, cache_misses, errors_4xx, errors_5xx)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (zone_id, hour_utc) DO UPDATE SET
          requests    = excluded.requests,
          bytes       = excluded.bytes,
          cache_hits  = excluded.cache_hits,
          cache_misses= excluded.cache_misses,
          errors_4xx  = excluded.errors_4xx,
          errors_5xx  = excluded.errors_5xx,
          inserted_at = datetime('now')
      `)
      .bind(
        zoneId, hourStr,
        row.requests, row.bytes,
        row.cachedRequests, row.requests - row.cachedRequests,
        row.status4xx, row.status5xx
      )
      .run();
    }
  },
};
```

## wrangler.toml cron and D1 binding

```toml
name = "metrics-export-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding  = "DB"
database_name = "metrics-store"
database_id   = "<your-d1-database-id>"

[triggers]
crons = ["0 * * * *"]   # top of every hour
```

## Querying retained history from D1

```sql
-- 30-day cache hit ratio trend
SELECT
  DATE(hour_utc) AS day,
  SUM(cache_hits) * 100.0 / NULLIF(SUM(requests), 0) AS cache_hit_pct,
  SUM(requests)   AS total_requests
FROM cf_zone_hourly
WHERE zone_id = 'abc123'
  AND hour_utc >= datetime('now', '-30 days')
GROUP BY day
ORDER BY day DESC;
```

---

## Anti-patterns

- **Fetching the current (open) hour**: GraphQL data for the current hour is
  incomplete. Always export `NOW() - 1 hour` to capture a fully closed window.
- **Fetching per-minute granularity for long history**: `httpRequests1mGroups`
  returns 10 000+ rows per zone per day; use `1hGroups` for archival to keep D1
  row counts and query costs manageable.
- **Storing raw JSON blobs**: column-per-metric schemas allow SQL aggregation
  without JSON parsing and are more efficient in SQLite.

## Gotchas

- The GraphQL Analytics API rate limit is 300 requests per 5 minutes per token. With
  many zones, batch carefully or use a single query with multiple `zones(filter:)`.
- `httpRequests1hGroups` data for the most recent hour may lag up to 15 minutes
  after the hour boundary; running the cron at `0 * * * *` may see incomplete data.
  Shift to `10 * * * *` (10 minutes past) for more reliable closed-window data.
- D1's `ON CONFLICT DO UPDATE` requires the conflicting column(s) to be part of the
  PRIMARY KEY or have a UNIQUE constraint; verify your migration applied correctly
  with `wrangler d1 execute`.
- The `responseStatusMap` field is not available on all Cloudflare plans; Enterprise
  zones have full access, Free/Pro may return null.

## Verification

```bash
# Confirm last inserted row
wrangler d1 execute metrics-store \
  --command "SELECT zone_id, hour_utc, requests, errors_5xx FROM cf_zone_hourly ORDER BY hour_utc DESC LIMIT 5"

# Manually trigger cron
wrangler dev --test-scheduled
```

Expected: rows for the last several hours with non-zero request counts.
If `requests = 0`, verify the zone tag and that the GraphQL token has
`Analytics: Read` permission scoped to the correct account.

## Related

- `analytics-engine-graphql-api-time-series-dashboard.md`
- `cloudflare-logpush-d1-log-aggregation.md`
- `d1-database-size-growth-analytics-engine.md`
- `workers-cron-trigger-missed-execution-alerting.md`

## Sources

- Cloudflare GraphQL Analytics API: https://developers.cloudflare.com/analytics/graphql-api/
- GraphQL schema explorer: https://api.cloudflare.com/client/v4/graphql (introspect via any GraphQL client)
- D1 SQL reference: https://developers.cloudflare.com/d1/reference/sql-api/
- Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
