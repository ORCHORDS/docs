# P50/P95/P99 Latency Percentile Tracking with Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker's average response time looks healthy, but users are reporting slow page loads. Average latency masks the long tail. You need per-route P50, P95, and P99 latency tracking and automated alerting when P95 breaches an SLO.

## Context

Cloudflare Analytics Engine supports the `quantile(p)(column)` aggregate function in its SQL API. By writing each request's wall-clock duration as a `double` and the route name as a `blob`, you can query true percentiles over any time window without maintaining a histogram yourself. The Cron Trigger polls the AE SQL API on a schedule and posts to Slack when a route's P95 exceeds the defined threshold.

Design:
- `blob1` = route identifier (e.g. `/api/users`, `/api/checkout`)
- `blob2` = HTTP method
- `blob3` = HTTP status code (string)
- `double1` = request duration in milliseconds

---

## Recording Request Latency in Your Worker

```typescript
// src/latency-tracker.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

/**
 * Middleware that wraps a fetch handler, records latency to Analytics Engine,
 * and returns the original response unchanged.
 */
export function withLatencyTracking(
  handler: (req: Request, env: Env) => Promise<Response>,
  routePattern: string
) {
  return async (request: Request, env: Env): Promise<Response> => {
    const start = performance.now();
    let status = 500;
    try {
      const response = await handler(request, env);
      status = response.status;
      return response;
    } finally {
      const durationMs = performance.now() - start;
      env.ANALYTICS.writeDataPoint({
        blobs: [
          routePattern,               // blob1 — route
          request.method,             // blob2 — HTTP method
          String(status),             // blob3 — status code
        ],
        doubles: [
          durationMs,                 // double1 — duration in ms
        ],
        indexes: [routePattern],      // enables per-route AE filtering
      });
    }
  };
}

// Usage:
const handleUsers = async (req: Request, env: Env) => {
  // … business logic …
  return Response.json({ users: [] });
};

export default {
  fetch: withLatencyTracking(handleUsers, '/api/users'),
};
```

---

## Querying P50 / P95 / P99 per Route

```typescript
// src/percentile-query.ts
export async function getLatencyPercentiles(
  accountId: string,
  apiToken: string,
  windowHours = 24
): Promise<Record<string, unknown>[]> {
  const sql = `
    SELECT
      blob1                           AS route,
      COUNT(*)                        AS requests,
      ROUND(quantile(0.50)(double1), 1) AS p50_ms,
      ROUND(quantile(0.95)(double1), 1) AS p95_ms,
      ROUND(quantile(0.99)(double1), 1) AS p99_ms,
      ROUND(AVG(double1), 1)            AS avg_ms
    FROM latency_tracking
    WHERE timestamp >= NOW() - INTERVAL '${windowHours}' HOUR
      AND blob3 NOT IN ('499')
    GROUP BY blob1
    ORDER BY p95_ms DESC
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!resp.ok) {
    throw new Error(`AE SQL failed: ${resp.status} ${await resp.text()}`);
  }

  const json = await resp.json() as { data: Record<string, unknown>[] };
  return json.data;
}
```

---

## Cron Trigger: Alert When P95 Exceeds SLO

```typescript
// src/slo-alerter.ts
// wrangler.toml: [[triggers]] crons = ["*/15 * * * *"]   (every 15 minutes)

interface SloConfig {
  route: string;
  p95SloMs: number;
}

const SLO_CONFIG: SloConfig[] = [
  { route: '/api/checkout',  p95SloMs: 800  },
  { route: '/api/users',     p95SloMs: 200  },
  { route: '/api/products',  p95SloMs: 300  },
];

export interface AlertEnv {
  CF_ACCOUNT_ID: string;
  AE_API_TOKEN: string;
  SLACK_WEBHOOK: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: AlertEnv): Promise<void> {
    const rows = await getLatencyPercentiles(env.CF_ACCOUNT_ID, env.AE_API_TOKEN, 1);

    const breaches: string[] = [];

    for (const config of SLO_CONFIG) {
      const row = rows.find((r) => r['route'] === config.route);
      if (!row) continue;

      const p95 = row['p95_ms'] as number;
      if (p95 > config.p95SloMs) {
        breaches.push(
          `• \`${config.route}\`  P95=${p95}ms  SLO=${config.p95SloMs}ms  ` +
          `(+${Math.round(p95 - config.p95SloMs)}ms over)`
        );
      }
    }

    if (breaches.length === 0) return;

    await fetch(env.SLACK_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text:
          `:rotating_light: *P95 SLO breach detected* (last 1 hour)\n` +
          breaches.join('\n'),
      }),
    });
  },
};
```

---

## Segmenting by Route in a Router Worker

When your Worker handles many routes, extract the route pattern before the handler runs so the analytics blob is always a fixed string, not a parameterised URL:

```typescript
function extractRoute(url: URL): string {
  // Replace numeric IDs with ':id' to avoid high-cardinality blobs
  return url.pathname
    .replace(/\/\d+/g, '/:id')
    .replace(/\/[0-9a-f-]{36}/g, '/:uuid');
}
```

High-cardinality blobs (e.g. per-user URLs) will fragment your percentile data across thousands of groups and produce statistically meaningless P99 values per group.

---

## Anti-patterns

- **Tracking only average latency** — averages are dominated by the median and hide tail behaviour entirely; a single 10-second request is invisible in an average of 1000 fast requests.
- **Using `blob1` as a raw `request.url`** — includes query strings and path parameters, creating unbounded cardinality and meaningless per-row percentiles.
- **Alerting on P99 for low-traffic routes** — P99 from 50 requests per hour is not statistically meaningful; gate alerts on a minimum `requests` count.
- **Writing latency from the Tail Worker** — adds Tail Worker processing time to the measurement; always record `performance.now()` delta inside the primary Worker.

## Gotchas

- Analytics Engine quantile functions require at least a handful of data points to return a meaningful result; queries over very short windows on low-traffic routes may return `null`.
- The AE propagation delay (~60s) means your 15-minute cron window will always miss the last minute of data — account for this by querying a slightly wider window (e.g. last 70 minutes instead of 60).
- `performance.now()` resolution in Workers is clamped to 0.1 ms for security reasons.
- AE SQL `quantile` syntax: `quantile(0.95)(column_name)` — note the double parentheses.

## Verification

1. Send 20+ requests to the monitored route (mix fast and slow responses if possible).
2. Wait 90 seconds for AE propagation.
3. Run the percentile SQL query manually via `curl` against the AE SQL API.
4. Confirm `p50_ms`, `p95_ms`, `p99_ms` columns are non-null and sensible.
5. Temporarily lower a SLO threshold to trigger the Slack alert and confirm delivery.

## Related

- `workers-analytics-engine-funnel-analysis.md`
- `cloudflare-synthetic-monitoring-cron-workers.md`
- `d1-slow-query-detection-tail-workers.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- https://developers.cloudflare.com/workers/runtime-apis/performance/
