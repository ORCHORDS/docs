# Analytics Engine SQL API: Querying AE Data and Materialising to D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You write high-cardinality event data (API calls, feature flags, user events) to Analytics Engine from Workers and need to query aggregates — daily active users, error rates, p95 latency — without paying for a time-series SaaS. The AE SQL API lets you query AE data with SQL; a scheduled Worker can materialise results to D1 for dashboards and alerting.

## Context

Cloudflare Analytics Engine (AE) is a columnar write-once time-series store exposed via `AnalyticsEngineDataset` binding. Each `writeDataPoint()` call stores up to 3 text blobs, 1 index string, and 20 numeric `doubles`. Data is queryable via a REST SQL API at `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`. The API accepts ClickHouse-dialect SQL via POST body. Retention is 31 days by default; results can be materialised to D1 for longer retention.

---

## Section 1 — Writing Data Points from a Worker

```toml
# wrangler.toml
name = "ae-demo"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[analytics_engine_datasets]]
binding  = "AE"
dataset  = "api_events"
```

```typescript
// src/index.ts
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';

interface Env {
  AE: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const start = Date.now();
    // ... handle request ...
    const durationMs = Date.now() - start;
    const status = 200;

    const url = new URL(request.url);

    // AE writeDataPoint: fire-and-forget, never awaited
    env.AE.writeDataPoint({
      // index1 is used for high-cardinality partition key (e.g., route)
      indexes: [url.pathname],
      // Up to 3 text blobs
      blobs: [
        request.method,           // blob1: HTTP method
        String(status),           // blob2: status code
        request.headers.get('cf-ipcountry') ?? 'XX',  // blob3: country
      ],
      // Up to 20 numeric doubles
      doubles: [
        durationMs,               // double1: latency ms
        Number(request.headers.get('content-length') ?? 0),  // double2: request bytes
      ],
    });

    return new Response('ok', { status });
  },
};
```

---

## Section 2 — Querying AE via the SQL API

The SQL API accepts ClickHouse-flavored SQL. Column names follow a positional convention: `blob1`, `blob2`, `blob3`, `double1`…`double20`, `index1`, `timestamp`.

```bash
# Ad-hoc query: requests per route in the last hour
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: text/plain" \
  --data "SELECT
    index1                        AS route,
    blob2                         AS status,
    count()                       AS requests,
    quantile(0.95)(double1)       AS p95_ms,
    avg(double1)                  AS avg_ms
  FROM api_events
  WHERE timestamp > NOW() - INTERVAL '1' HOUR
    AND dataset = 'api_events'
  GROUP BY route, status
  ORDER BY requests DESC
  LIMIT 50"
```

```typescript
// src/ae-client.ts — reusable AE SQL query helper
export interface AEQueryResult<T> {
  data: T[];
  rows: number;
  rows_before_limit_at_least: number;
  meta: { name: string; type: string }[];
}

export async function queryAE<T = Record<string, unknown>>(
  accountId: string,
  apiToken: string,
  sql: string
): Promise<AEQueryResult<T>> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'text/plain',
      },
      body: sql,
    }
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`AE SQL API ${res.status}: ${body}`);
  }

  return res.json() as Promise<AEQueryResult<T>>;
}
```

---

## Section 3 — Scheduled Worker: Materialise Daily Aggregates to D1

```sql
-- migrations/0001_ae_aggregates.sql
CREATE TABLE IF NOT EXISTS daily_api_stats (
  day          TEXT NOT NULL,
  route        TEXT NOT NULL,
  status       TEXT NOT NULL,
  requests     INTEGER NOT NULL,
  avg_ms       REAL NOT NULL,
  p95_ms       REAL NOT NULL,
  synced_at    TEXT NOT NULL,
  PRIMARY KEY (day, route, status)
);
```

```toml
# wrangler.toml additions
[triggers]
crons = ["0 1 * * *"]  # daily at 01:00 UTC

[[d1_databases]]
binding       = "DB"
database_name = "ae-materialised"
database_id   = "<your-d1-id>"

[vars]
ACCOUNT_ID = "<your-account-id>"
```

```typescript
// src/materialise.ts
import type { D1Database, ScheduledEvent, ExecutionContext } from '@cloudflare/workers-types';
import { queryAE } from './ae-client';

interface Env {
  DB: D1Database;
  ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}

interface DailyRow {
  day: string;
  route: string;
  status: string;
  requests: number;
  avg_ms: number;
  p95_ms: number;
}

async function materialiseYesterday(env: Env): Promise<void> {
  // ClickHouse toStartOfDay for yesterday
  const sql = `
    SELECT
      toString(toStartOfDay(timestamp))   AS day,
      index1                              AS route,
      blob2                               AS status,
      count()                             AS requests,
      avg(double1)                        AS avg_ms,
      quantile(0.95)(double1)             AS p95_ms
    FROM api_events
    WHERE timestamp >= toStartOfDay(yesterday())
      AND timestamp <  toStartOfDay(today())
    GROUP BY day, route, status
    ORDER BY requests DESC
    LIMIT 10000
  `;

  const result = await queryAE<DailyRow>(env.ACCOUNT_ID, env.CF_API_TOKEN, sql);

  if (result.data.length === 0) {
    console.log('[materialise] No data for yesterday');
    return;
  }

  const now = new Date().toISOString();
  const stmt = env.DB.prepare(`
    INSERT OR REPLACE INTO daily_api_stats
      (day, route, status, requests, avg_ms, p95_ms, synced_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `);

  const batch = result.data.map((row) =>
    stmt.bind(row.day, row.route, row.status, row.requests, row.avg_ms, row.p95_ms, now)
  );

  // D1 batch is capped at 100 per call; chunk if necessary
  const CHUNK = 100;
  for (let i = 0; i < batch.length; i += CHUNK) {
    await env.DB.batch(batch.slice(i, i + CHUNK));
  }

  console.log(`[materialise] wrote ${result.data.length} rows to D1`);
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await materialiseYesterday(env);
  },
};
```

---

## Section 4 — Dashboard Query on Materialised D1 Data

```typescript
// src/dashboard-api.ts — expose aggregated stats via HTTP
import type { D1Database } from '@cloudflare/workers-types';

interface Env { DB: D1Database; }

export async function handleDashboard(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const days = Number(url.searchParams.get('days') ?? 7);

  const rows = await env.DB.prepare(`
    SELECT
      day,
      route,
      SUM(requests)       AS total_requests,
      AVG(avg_ms)         AS avg_latency_ms,
      MAX(p95_ms)         AS p95_latency_ms,
      SUM(CASE WHEN CAST(status AS INTEGER) >= 500 THEN requests ELSE 0 END) AS errors
    FROM daily_api_stats
    WHERE day >= date('now', '-' || ? || ' days')
    GROUP BY day, route
    ORDER BY day DESC, total_requests DESC
  `)
    .bind(days)
    .all();

  return Response.json(rows.results, {
    headers: { 'Cache-Control': 'public, max-age=300' },
  });
}
```

---

## Anti-patterns

- **Awaiting `writeDataPoint()`** — it returns `void`, not a Promise. Never `await` it; doing so silently resolves immediately without error but is misleading.
- **Using AE for user-facing real-time queries** — AE has a ~5 minute write lag. Cache materialized views in D1; do not query AE on the hot path.
- **Querying without `dataset` filter** — always include `WHERE dataset = 'your_dataset'` to avoid cross-dataset scans.
- **Sending more than 20 doubles or 3 blobs** — excess fields are silently dropped by the runtime.

## Gotchas

- AE SQL uses **ClickHouse dialect**, not SQLite/PostgreSQL. Functions like `quantile()`, `toStartOfDay()`, and `yesterday()` are ClickHouse-specific.
- The API token needs the **Account Analytics: Read** permission.
- D1 `batch()` is limited to **100 statements per call**. Chunk your inserts.
- AE data is retained for **31 days**. Schedule the materialisation Worker to run daily before midnight UTC.
- The `index1` field is the partition key for AE's columnar storage. Use it for the column you will filter on most frequently (e.g., route, tenant ID).

## Verification

```bash
# Quick ad-hoc count
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: text/plain" \
  --data "SELECT count() FROM api_events WHERE timestamp > NOW() - INTERVAL '5' MINUTE" \
  | jq '.data'

# Trigger scheduled worker locally
wrangler dev --test-scheduled
curl 'http://localhost:8787/__scheduled?cron=0+1+*+*+*'

# Check D1 result
wrangler d1 execute ae-materialised --remote \
  --command "SELECT day, COUNT(*) as routes FROM daily_api_stats GROUP BY day ORDER BY day DESC LIMIT 5;"
```

## Related

- `cloudflare-ai-gateway-prompt-logging-d1.md` — writing AI Gateway cost data alongside AE metrics
- `workers-durable-objects-sqlite-api.md` — per-entity counters that feed into AE datasets

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
