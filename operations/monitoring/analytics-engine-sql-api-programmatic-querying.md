# Programmatic Querying of Workers Analytics Engine via the SQL API

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

The Cloudflare dashboard exposes Analytics Engine data through a fixed UI. Teams building internal ops dashboards, Slack digests, or custom alerting pipelines need to query the dataset programmatically. The Analytics Engine SQL-over-HTTP API accepts standard SQL with ClickHouse-compatible aggregate functions and returns JSON, enabling any language or tool to consume real-time Workers telemetry.

## Context

Analytics Engine exposes a single HTTP endpoint at `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`. It accepts a POST body with a `query` field containing a SQL statement. Authentication is via a Cloudflare API token scoped to `Account Analytics: Read`. The result envelope contains a `data` array of row objects and a `meta` array describing column types. Queries execute against a ClickHouse-like engine; most standard SQL aggregates, window functions, and `WITH` CTEs are supported. There is no streaming — results are returned synchronously up to a 1 000 000-row scan budget per query.

## Type-Safe Query Client

```typescript
// lib/analytics-engine-client.ts
interface AEQueryResult<T> {
  data: T[];
  meta: { name: string; type: string }[];
  rows: number;
  rows_before_limit_at_least: number;
}

export class AnalyticsEngineClient {
  private readonly baseUrl: string;
  private readonly headers: HeadersInit;

  constructor(accountId: string, apiToken: string) {
    this.baseUrl = `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`;
    this.headers = {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    };
  }

  async query<T = Record<string, unknown>>(sql: string): Promise<AEQueryResult<T>> {
    const res = await fetch(this.baseUrl, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ query: sql }),
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`AE query error ${res.status}: ${body}`);
    }

    return res.json() as Promise<AEQueryResult<T>>;
  }

  async queryRows<T = Record<string, unknown>>(sql: string): Promise<T[]> {
    const result = await this.query<T>(sql);
    return result.data;
  }
}
```

## Common Query Patterns

```typescript
// queries/worker-health.ts
import { AnalyticsEngineClient } from "../lib/analytics-engine-client.js";

export interface WorkerHealthRow {
  route: string;
  requests: number;
  error_rate: number;
  p50_ms: number;
  p99_ms: number;
}

export async function getWorkerHealth(
  client: AnalyticsEngineClient,
  lookbackHours = 1,
): Promise<WorkerHealthRow[]> {
  return client.queryRows<WorkerHealthRow>(`
    SELECT
      blob1                                              AS route,
      count()                                            AS requests,
      countIf(double2 >= 500) / count()                 AS error_rate,
      quantileWeighted(0.50)(double1, 1)                AS p50_ms,
      quantileWeighted(0.99)(double1, 1)                AS p99_ms
    FROM worker_requests
    WHERE timestamp >= now() - INTERVAL '${lookbackHours}' HOUR
    GROUP BY route
    HAVING requests > 10
    ORDER BY error_rate DESC, p99_ms DESC
    LIMIT 100
  `);
}

// Time-series bucketing for sparklines
export interface BucketRow {
  bucket: string;
  requests: number;
  errors: number;
}

export async function getRequestTimeSeries(
  client: AnalyticsEngineClient,
  route: string,
  bucketMinutes = 5,
): Promise<BucketRow[]> {
  return client.queryRows<BucketRow>(`
    SELECT
      toStartOfInterval(timestamp, INTERVAL '${bucketMinutes}' MINUTE) AS bucket,
      count()                                                           AS requests,
      countIf(double2 >= 500)                                          AS errors
    FROM worker_requests
    WHERE timestamp >= now() - INTERVAL '6' HOUR
      AND blob1 = '${route.replace(/'/g, "''")}'
    GROUP BY bucket
    ORDER BY bucket ASC
  `);
}
```

## Scheduled Digest Worker (Pushes to Slack)

```typescript
// workers/health-digest/index.ts
import { AnalyticsEngineClient } from "../../lib/analytics-engine-client.js";
import { getWorkerHealth } from "../../queries/worker-health.js";

export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  SLACK_WEBHOOK_URL: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const client = new AnalyticsEngineClient(env.CF_ACCOUNT_ID, env.CF_API_TOKEN);
    const rows = await getWorkerHealth(client, 1);

    const highError = rows.filter((r) => r.error_rate > 0.01);
    const highLatency = rows.filter((r) => r.p99_ms > 2000);

    if (highError.length === 0 && highLatency.length === 0) return;  // suppress clean digests

    const lines: string[] = ["*Workers health digest (last 1 h)*"];

    if (highError.length) {
      lines.push("\n*High error rate routes:*");
      for (const r of highError.slice(0, 5)) {
        lines.push(`• \`${r.route}\` — ${(r.error_rate * 100).toFixed(1)}% errors, ${r.requests} req`);
      }
    }

    if (highLatency.length) {
      lines.push("\n*High p99 latency routes:*");
      for (const r of highLatency.slice(0, 5)) {
        lines.push(`• \`${r.route}\` — p99 ${r.p99_ms.toFixed(0)} ms`);
      }
    }

    await fetch(env.SLACK_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: lines.join("\n") }),
    });
  },
};
```

## Rate Limits and Pagination Strategy

```typescript
// Analytics Engine SQL API limits: 1 000 req/min per account, 1 M row scan per query.
// For large datasets, paginate using ORDER BY + cursor offsets.

export async function paginatedQuery<T>(
  client: AnalyticsEngineClient,
  baseQuery: string,
  pageSize = 10_000,
): Promise<T[]> {
  const allRows: T[] = [];
  let offset = 0;

  while (true) {
    const page = await client.queryRows<T>(
      `${baseQuery} LIMIT ${pageSize} OFFSET ${offset}`,
    );
    allRows.push(...page);
    if (page.length < pageSize) break;
    offset += pageSize;
  }

  return allRows;
}
```

## Anti-patterns

- Interpolating user-supplied strings directly into SQL without escaping — Analytics Engine has no parameterised query support; sanitise all dynamic values, especially route or tag strings sourced from user input.
- Querying without a `WHERE timestamp >=` clause — a full-table scan hits the row budget instantly on busy datasets and returns a 400 error.
- Polling the SQL API on every incoming HTTP request to a public endpoint — results should be cached in Workers KV or a Durable Object, not fetched per-request.

## Gotchas

- Column names in the result match the aliases in the `SELECT` clause, not the underlying blob/double field names — always use explicit `AS` aliases.
- The API token must have `Account Analytics: Read` permission; the standard `Workers: Edit` token does not include it.
- `toStartOfInterval` bucketing in the WHERE clause does not use the index; filter on raw `timestamp` and group on the truncated value for best performance.

## Verification

```bash
# Smoke-test connectivity and auth
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT 1 AS health"}' \
  | jq '.data'

# Count data points written in the last hour
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"query":"SELECT count() AS n FROM worker_requests WHERE timestamp > now() - INTERVAL '\''1'\'' HOUR"}' \
  | jq '.data[0].n'
```

## Related

- `monitoring/cloudflare-analytics-engine.md`
- `monitoring/rum-beacon-workers-analytics-engine.md`
- `monitoring/performance-regression-ci-workers-baseline.md`
- `monitoring/cloudflare-analytics-engine-grafana-dashboard.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-reference/
- https://developers.cloudflare.com/analytics/analytics-engine/limits/
