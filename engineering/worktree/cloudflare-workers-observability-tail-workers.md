# Cloudflare Workers Observability: Tail Workers and Analytics Engine

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your production Worker returns intermittent 500 errors. `wrangler tail` captures some of them, but you can only watch one terminal at a time, the output disappears when you close it, there is no structured querying, and tail sampling drops events at high traffic. You need durable, structured, queryable observability that survives across deploys and is available to everyone on the team — not just the person with a terminal open.

---

## Context

Cloudflare offers two complementary observability primitives for Workers:

**Tail Workers** are Workers invoked after every request your main Worker handles. They receive a `TraceItem` object containing the request, response, logs, exceptions, CPU time, and wall time from the original invocation. Tail Workers run asynchronously in their own isolate — they do not block the original request. They are the production-grade replacement for `wrangler tail`.

**Analytics Engine** is a time-series columnar store built into the Workers runtime. You write data points (called "data events") using the `writeDataPoint()` API on an `AnalyticsEngineDataset` binding. Data is queryable via the Cloudflare GraphQL API or the Analytics Engine SQL API within seconds of writing.

Together: your main Worker generates logs and metrics; a Tail Worker ships them durably to Analytics Engine (and optionally to external destinations like Datadog, Splunk, or an R2 archive).

---

## Section 1: Architecture Overview

```
                 ┌─────────────────────┐
  HTTP request → │   Main Worker       │ → HTTP response (not delayed)
                 │  (api-worker)       │
                 └──────────┬──────────┘
                            │ async, after response
                            ▼
                 ┌─────────────────────┐
                 │   Tail Worker       │
                 │  (observability-    │
                 │   worker)           │
                 └──┬──────────┬───────┘
                    │          │
                    ▼          ▼
           Analytics      External sink
           Engine         (R2 archive,
           Dataset         Datadog, etc.)
```

---

## Section 2: Setting Up the Tail Worker

Create a dedicated package in your monorepo for the Tail Worker:

```
packages/observability-worker/
├── src/
│   └── index.ts
└── wrangler.toml
```

```toml
# packages/observability-worker/wrangler.toml
name            = "observability-worker"
main            = "src/index.ts"
compatibility_date = "2026-01-01"

[[analytics_engine_datasets]]
binding         = "EVENTS"
dataset         = "workers_events"

[[r2_buckets]]
binding         = "ARCHIVE"
bucket_name     = "workers-logs-archive"
```

Declare the Tail Worker in the main Worker's `wrangler.toml`:

```toml
# packages/api-worker/wrangler.toml
name            = "api-worker"
main            = "src/index.ts"
compatibility_date = "2026-01-01"

tail_consumers = [
  { service = "observability-worker" }
]
```

---

## Section 3: Tail Worker Implementation

```typescript
// packages/observability-worker/src/index.ts

interface Env {
  EVENTS: AnalyticsEngineDataset;
  ARCHIVE: R2Bucket;
}

// TraceItem is the shape of each invocation in the tail batch
interface TraceItem {
  event: {
    request: {
      url: string;
      method: string;
      headers: Record<string, string>;
      cf?: Record<string, unknown>;
    };
    response?: { status: number };
  };
  eventTimestamp: number;
  logs: Array<{ message: unknown[]; level: string; timestamp: number }>;
  exceptions: Array<{ name: string; message: string; timestamp: number }>;
  outcome:
    | "ok"
    | "exception"
    | "exceededCpu"
    | "exceededMemory"
    | "unknown"
    | "canceled"
    | "scriptNotFound";
  scriptName: string;
  cpuTime: number;  // milliseconds
  wallTime: number; // milliseconds
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const url = new URL(event.event.request.url);
      const status = event.event.response?.status ?? 0;
      const country = String(
        (event.event.request.cf?.country as string) ?? "unknown"
      );
      const isError = status >= 500 || event.outcome !== "ok";

      // Write structured data point to Analytics Engine
      env.EVENTS.writeDataPoint({
        blobs: [
          url.pathname,                     // index1: path
          event.event.request.method,       // index2: method
          country,                          // index3: country
          event.outcome,                    // index4: outcome
          event.scriptName,                 // index5: worker name
          event.exceptions[0]?.name ?? "",  // index6: exception class (if any)
        ],
        doubles: [
          status,              // double1: HTTP status code
          event.cpuTime,       // double2: CPU time (ms)
          event.wallTime,      // double3: wall time (ms)
          isError ? 1 : 0,     // double4: error flag
          event.logs.length,   // double5: log line count
        ],
        indexes: [
          // Primary index for fan-out queries (max 96 bytes, string)
          `${event.scriptName}:${url.pathname.split("/")[1] ?? ""}`,
        ],
      });

      // Archive full event payload to R2 for audit / replay
      if (isError) {
        const key = `errors/${event.scriptName}/${new Date(event.eventTimestamp).toISOString().split("T")[0]}/${event.eventTimestamp}.json`;
        await env.ARCHIVE.put(
          key,
          JSON.stringify({
            ...event,
            // Redact auth headers before archiving
            event: {
              ...event.event,
              request: {
                ...event.event.request,
                headers: redactHeaders(event.event.request.headers),
              },
            },
          }),
          { httpMetadata: { contentType: "application/json" } }
        );
      }
    }
  },
};

function redactHeaders(
  headers: Record<string, string>
): Record<string, string> {
  const redacted = ["authorization", "cookie", "x-api-key"];
  return Object.fromEntries(
    Object.entries(headers).map(([k, v]) => [
      k,
      redacted.includes(k.toLowerCase()) ? "[REDACTED]" : v,
    ])
  );
}
```

---

## Section 4: Structured Logging from the Main Worker

Log structured data that the Tail Worker will forward. Use `console.log` with a JSON shape:

```typescript
// packages/api-worker/src/lib/logger.ts
export function log(
  level: "debug" | "info" | "warn" | "error",
  message: string,
  context?: Record<string, unknown>
): void {
  // Tail Worker captures all console output; use JSON for structure
  consolelevel);
}

// Usage in handlers
export async function handleOrder(
  request: Request,
  env: Env
): Promise<Response> {
  const { orderId } = await request.json<{ orderId: string }>();
  log("info", "processing order", { orderId, path: "/orders" });

  try {
    const order = await processOrder(env.DB, orderId);
    log("info", "order processed", { orderId, total: order.total });
    return Response.json(order);
  } catch (err) {
    log("error", "order processing failed", {
      orderId,
      error: err instanceof Error ? err.message : String(err),
    });
    throw err; // Let the Tail Worker capture the exception
  }
}
```

---

## Section 5: Querying Analytics Engine

Use the SQL API (BETA as of 2026) or GraphQL API to query collected events:

```bash
# Set up environment
export CF_ACCOUNT_ID="your-account-id"
export CF_API_TOKEN="your-analytics-read-token"

# Request counts by path (last 24h)
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  --data-urlencode "query=
    SELECT
      blob1 AS path,
      SUM(_sample_interval) AS requests,
      AVG(double3) AS avg_wall_ms,
      SUM(CASE WHEN double4 = 1 THEN _sample_interval ELSE 0 END) AS errors
    FROM workers_events
    WHERE timestamp >= now() - INTERVAL '24' HOUR
      AND blob5 = 'api-worker'
    GROUP BY path
    ORDER BY requests DESC
    LIMIT 20
  "
```

```bash
# P95 latency per HTTP method
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  --data-urlencode "query=
    SELECT
      blob2 AS method,
      quantileWeighted(0.95)(double3, _sample_interval) AS p95_wall_ms,
      quantileWeighted(0.99)(double3, _sample_interval) AS p99_wall_ms
    FROM workers_events
    WHERE timestamp >= now() - INTERVAL '1' HOUR
    GROUP BY method
  "
```

---

## Section 6: Alerting with Cloudflare Notifications

Set threshold alerts without external services using Cloudflare Notifications (dashboard: Notifications → Add Notification → Workers):

- **Error rate spike:** `errors / requests > 0.05` over 5 minutes
- **CPU time threshold:** P95 CPU > 10ms sustained for 10 minutes
- **Tail Worker failure:** tail consumer delivery failures (reported in Worker analytics dashboard)

For PagerDuty/Slack, use a dedicated alerting Worker that polls the Analytics Engine SQL API on a cron trigger:

```toml
# packages/alerting-worker/wrangler.toml
name = "alerting-worker"
main = "src/index.ts"

[triggers]
crons = ["*/5 * * * *"]   # Every 5 minutes

[[analytics_engine_datasets]]
binding = "EVENTS"
dataset = "workers_events"
```

```typescript
// packages/alerting-worker/src/index.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const errorRate = await queryErrorRate(env, 5); // last 5 minutes
    if (errorRate > 0.05) {
      await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        body: JSON.stringify({
          text: `*Alert:* api-worker error rate is ${(errorRate * 100).toFixed(1)}% (threshold: 5%)`,
        }),
      });
    }
  },
};
```

---

## Anti-patterns

- **Using `wrangler tail` as the only observability tool.** Tail sessions drop events when the CLI disconnects, have ~10% sampling at high traffic, and are not searchable. Use Tail Workers for production observability.
- **Logging PII or credentials.** Tail Workers forward all console output and request headers to Analytics Engine. Redact before writing, especially auth tokens, cookies, and email addresses.
- **Writing a data point per log line.** Analytics Engine has a write limit. Write one data point per request (in the Tail Worker), aggregating log lines and exceptions into blobs.
- **Using Analytics Engine for audit logs.** Data in Analytics Engine is retained for 90 days. For compliance/audit, archive raw events to R2 where retention is configurable.
- **Deploying the Tail Worker and main Worker from the same pipeline step.** If the Tail Worker deploy fails, the `tail_consumers` reference is broken. Deploy the Tail Worker first, then the main Worker.

---

## Gotchas

- Analytics Engine data points have limits: 20 blobs (max 1024 bytes each), 20 doubles, 1 index (max 96 bytes). Exceeding these silently truncates the data point.
- The Tail Worker receives events in batches of up to 100 trace items. Handle batch processing — do not assume one event per invocation.
- Tail Workers do not receive tail events from other Tail Workers (no infinite loops), but they can tail themselves if misconfigured via `tail_consumers` pointing to the same Worker.
- `wrangler tail` and a Tail Worker can coexist; both receive the same events. The `wrangler tail` session is filtered separately.
- Analytics Engine `quantileWeighted` requires `_sample_interval` as the weight parameter for statistically correct aggregation when sampling is active.
- Tail Worker CPU time is billed separately from the main Worker. A Tail Worker with expensive R2 writes on every error can become costly at scale — batch and filter.

---

## Verification

```bash
# Deploy Tail Worker first
pnpm --filter observability-worker exec wrangler deploy --env production

# Deploy main Worker (references Tail Worker via tail_consumers)
pnpm --filter api-worker exec wrangler deploy --env production

# Verify tail consumer is registered
wrangler tail api-worker --env production 2>&1 | head -5
# Should show: "Successfully created tail..."

# Generate a test error
curl -X POST https://api.example.com/test-error -d '{}'

# Query Analytics Engine for the error (allow ~30s for propagation)
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  --data-urlencode "query=
    SELECT blob1, double1, double4
    FROM workers_events
    WHERE timestamp >= now() - INTERVAL '5' MINUTE
    ORDER BY timestamp DESC
    LIMIT 5
  "
```

---

## Related

- `cloudflare-workers-vitest-miniflare-testing.md` — catching errors before production
- `wrangler-environments-staging-production.md` — separate Tail Workers per environment
- `workers-kv-r2-d1-storage-selection.md` — R2 for log archival
- `github-actions-wrangler-deploy-pipeline.md` — deploy ordering (Tail Worker before main Worker)
- `on-call-playbook-template.md` — how to use these logs during incidents

---

## Sources

- Cloudflare Tail Workers docs — https://developers.cloudflare.com/workers/observability/tail-workers/
- Analytics Engine docs — https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare Notifications — https://developers.cloudflare.com/notifications/
