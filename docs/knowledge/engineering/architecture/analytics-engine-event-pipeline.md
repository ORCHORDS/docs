# Event-Driven Analytics Pipeline with Cloudflare Analytics Engine

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You run a SaaS product on Cloudflare Workers and need sub-second analytics: page views, feature
usage events, API latency histograms, tenant activity counters. Forwarding events to an external
provider (Segment, Mixpanel, DataDog) adds egress cost, introduces a synchronous HTTP call on
every request path, and creates a hard dependency on a third-party SLA. You want analytics that
are native to the edge, free of round-trip latency, and queryable in real time via SQL.

Cloudflare Analytics Engine is a write-optimised, time-series–capable SQL store built into the
Workers runtime. It accepts `writeDataPoint` calls with zero async overhead, batches internally,
and exposes a GraphQL and SQL API for querying aggregates.

---

## Context

**Analytics Engine data model** — each data point has:
- Up to 20 `indexes` (string labels, up to 96 bytes each): equivalent to tags/dimensions
- Up to 20 `doubles` (float64 numbers): metrics/measurements
- Up to 20 `blobs` (arbitrary byte strings up to 1 KB): unstructured payloads
- An implicit `timestamp` (nanosecond precision, set at write time)

Data is retained for 90 days (free plan: 6 months on paid). You query via the
`/v4/accounts/{account_id}/analytics_engine/sql` REST endpoint or the GraphQL Analytics API.

The key architectural insight: `writeDataPoint` is **fire-and-forget in the Worker runtime** —
it never blocks the response. The platform batches points and flushes asynchronously after the
response is sent, so it adds zero latency to your critical path.

---

## 1. Instrumented Worker — Writing Data Points

```typescript
// src/analytics.ts
export interface AnalyticsEvent {
  type: string;           // e.g. "api_request", "feature_used", "error"
  tenantId: string;
  userId?: string;
  route?: string;
  statusCode?: number;
  durationMs?: number;
  errorCode?: string;
  metadata?: string;      // JSON-encoded extra context (≤1 KB)
}

/**
 * Write an analytics event to Analytics Engine.
 * writeDataPoint is synchronous and non-blocking — no await needed.
 */
export function trackEvent(
  dataset: AnalyticsEngineDataset,
  event: AnalyticsEvent
): void {
  dataset.writeDataPoint({
    // indexes[0..2]: high-cardinality dimensions used in GROUP BY
    indexes: [
      event.type,                        // index1
      event.tenantId,                    // index2
      event.route ?? '',                 // index3
      event.userId ?? '',                // index4
      String(event.statusCode ?? 0),     // index5
      event.errorCode ?? '',             // index6
    ],
    // doubles[0..2]: quantitative measurements
    doubles: [
      event.durationMs ?? 0,             // double1
      event.statusCode ?? 0,             // double2
      event.statusCode && event.statusCode >= 500 ? 1 : 0, // double3: is_error flag
    ],
    // blobs[0]: optional structured payload
    blobs: [
      event.metadata ? event.metadata.slice(0, 1024) : '',
    ],
  });
}

// src/index.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);

    let response: Response;
    let statusCode = 200;

    try {
      response = await routeRequest(request, env);
      statusCode = response.status;
    } catch (err) {
      statusCode = 500;
      response = new Response('Internal Server Error', { status: 500 });
    } finally {
      const durationMs = Date.now() - start;
      trackEvent(env.ANALYTICS, {
        type: 'api_request',
        tenantId: request.headers.get('x-tenant-id') ?? 'unknown',
        route: `${request.method} ${url.pathname}`,
        statusCode,
        durationMs,
      });
    }

    return response!;
  },
};
```

Bind the dataset in `wrangler.jsonc`:

```jsonc
{
  "analytics_engine_datasets": [
    {
      "binding": "ANALYTICS",
      "dataset": "api_events"
    }
  ]
}
```

---

## 2. Feature Usage Tracking with Tenant Attribution

Beyond HTTP metrics, track domain-level events — feature activations, upgrade prompts shown,
quota exhausted events — to power product analytics and billing dashboards.

```typescript
// src/feature-analytics.ts
import { trackEvent } from './analytics';

export function trackFeatureUsed(
  dataset: AnalyticsEngineDataset,
  opts: {
    tenantId: string;
    userId: string;
    feature: string;
    variant?: string;        // for A/B tests
    planTier?: string;
    unitsConsumed?: number;
  }
): void {
  trackEvent(dataset, {
    type: 'feature_used',
    tenantId: opts.tenantId,
    userId: opts.userId,
    route: opts.feature,
    metadata: JSON.stringify({
      variant: opts.variant,
      planTier: opts.planTier,
    }),
    durationMs: opts.unitsConsumed, // repurpose double1 as unit counter
  });
}

export function trackQuotaExceeded(
  dataset: AnalyticsEngineDataset,
  opts: { tenantId: string; feature: string; limit: number; consumed: number }
): void {
  trackEvent(dataset, {
    type: 'quota_exceeded',
    tenantId: opts.tenantId,
    route: opts.feature,
    errorCode: 'QUOTA_EXCEEDED',
    metadata: JSON.stringify({ limit: opts.limit, consumed: opts.consumed }),
  });
}
```

---

## 3. SQL Queries for Dashboards

Cloudflare exposes a SQL API at:
`https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`

```sql
-- P99 latency per route over the last 24 hours
SELECT
  index3 AS route,
  quantileWeighted(0.99)(double1, 1) AS p99_ms,
  quantileWeighted(0.50)(double1, 1) AS p50_ms,
  count()                             AS request_count
FROM api_events
WHERE
  timestamp > NOW() - INTERVAL '1' DAY
  AND index1 = 'api_request'
GROUP BY route
ORDER BY p99_ms DESC
LIMIT 20;
```

```sql
-- Error rate by tenant over the last hour
SELECT
  index2 AS tenant_id,
  sum(double3)    AS error_count,
  count()         AS total_requests,
  sum(double3) / count() * 100 AS error_rate_pct
FROM api_events
WHERE
  timestamp > NOW() - INTERVAL '1' HOUR
  AND index1 = 'api_request'
GROUP BY tenant_id
HAVING total_requests > 10   -- ignore tenants with too few samples
ORDER BY error_rate_pct DESC;
```

```sql
-- Feature adoption by plan tier (last 7 days)
SELECT
  index3 AS feature,
  JSONExtractString(blob1, 'planTier') AS plan_tier,
  count()                                AS activations,
  countDistinct(index4)                  AS unique_users
FROM api_events
WHERE
  timestamp > NOW() - INTERVAL '7' DAY
  AND index1 = 'feature_used'
GROUP BY feature, plan_tier
ORDER BY activations DESC;
```

Wrap these queries in a lightweight dashboard Worker that authenticates with the Cloudflare API
using a scoped token and streams results to your internal admin panel.

---

## 4. Alerting Pipeline with Queues

For near-real-time alerting (e.g., error rate > 5% for a tenant), poll Analytics Engine on a
schedule and fan out alerts via Queues:

```typescript
// alert-poller/src/index.ts
export interface Env {
  ALERT_QUEUE: Queue;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}

const ERROR_RATE_THRESHOLD = 0.05;

export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT index2 AS tenant_id,
             sum(double3) / count() AS error_rate
      FROM api_events
      WHERE timestamp > NOW() - INTERVAL '5' MINUTE
        AND index1 = 'api_request'
      GROUP BY tenant_id
      HAVING error_rate > ${ERROR_RATE_THRESHOLD}
    `;

    const response = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: sql }),
      }
    );

    const { data } = (await response.json()) as { data: Array<{ tenant_id: string; error_rate: number }> };

    await Promise.all(
      data.map((row) =>
        env.ALERT_QUEUE.send({
          type: 'high_error_rate',
          tenantId: row.tenant_id,
          errorRate: row.error_rate,
          detectedAt: new Date().toISOString(),
        })
      )
    );
  },
};
```

Schedule this Worker to run every 5 minutes via a Cron Trigger. The Queue consumer Worker
handles deduplication and notification dispatch (PagerDuty, Slack, email).

---

## Anti-patterns

- **Awaiting `writeDataPoint` results.** There is no return value; the call is fire-and-forget.
  Wrapping it in `await` does nothing but is misleading to future readers.
- **Writing high-cardinality user IDs as `index1`.** The first index is used as the primary
  shard key. High-cardinality values cause poor query performance. Put user IDs in `index4` or
  later; put low-cardinality event types in `index1`.
- **Encoding all data in a single JSON blob.** If you put all dimensions into `blob1` as JSON and
  skip indexes/doubles, you cannot `GROUP BY` or filter efficiently. Use indexes for dimensions
  you query and doubles for all numeric measurements.
- **Calling the SQL API from the hot request path.** SQL queries against Analytics Engine are
  analytical — they scan large amounts of data. Run them from scheduled Workers or admin
  backends, never inline in a user-facing request.
- **Exceeding 25 data points per `writeDataPoint` call.** The limit is 20 indexes, 20 doubles,
  20 blobs. Silently truncated values are worse than a schema error; validate your schema
  at build time.

---

## Gotchas

- **No transactions.** Each `writeDataPoint` is independent. There is no way to atomically write
  multiple related points. Design your schema so each event is self-contained.
- **90-day retention on free tier; configurable on paid.** Build a separate archival pipeline
  (to R2 + Parquet) if you need longer retention.
- **Eventual availability.** Data points appear in queries within 5–30 seconds of the Worker
  completing its response. Do not use Analytics Engine for operational metrics that must be
  real-time to the millisecond.
- **SQL dialect is ClickHouse-like.** Some standard SQL functions are not available; use
  `quantileWeighted`, `countDistinct`, and `JSONExtractString` — not `PERCENTILE_CONT`, `COUNT(DISTINCT)`, or `JSON_VALUE`.
- **Account-level billing.** Analytics Engine writes count toward your account-wide limit.
  Monitor usage with `GET /accounts/{id}/analytics_engine/datasets/{dataset}/stats`.

---

## Verification

```bash
# Write a test data point and confirm it appears
wrangler analytics-engine write \
  --dataset api_events \
  --indexes "test_event,tenant_abc" \
  --doubles "123.0,200.0,0.0"

# Query to confirm the write arrived (allow ~30s for availability)
curl -sX POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT count() FROM api_events WHERE index1 = '"'"'test_event'"'"' AND timestamp > NOW() - INTERVAL '"'"'5'"'"' MINUTE"}' \
  | jq '.data'

# Check dataset write stats
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/datasets/api_events/stats" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '{writes_last_hour: .result.writes_last_hour}'
```

---

## Related

- `event-driven-architecture-overview.md`
- `workers-queue-fanout-architecture.md`
- `rate-limiting-architecture-workers.md`
- `observability-architecture.md`
- `multi-tenancy-isolation-patterns.md`

---

## Sources

- Cloudflare Analytics Engine documentation: https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API reference: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- ClickHouse SQL reference (Analytics Engine dialect): https://clickhouse.com/docs/en/sql-reference/
- "Observability at the Edge" — Cloudflare Blog
