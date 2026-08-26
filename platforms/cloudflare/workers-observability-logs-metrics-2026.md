# workers-observability-logs-metrics-2026

Setting up production observability for Workers in 2026: structured logs via
Workers Logs, metrics via Workers Analytics Engine, and long-term export via
Logpush. This is the unified stack that replaces scattered `console.log` and
dashboard-staring.

## Symptom

Your Worker is failing in production but you can't figure out why:

- `wrangler tail` shows logs but they scroll by and disappear after the
  session ends
- The Cloudflare dashboard shows request counts but not error rates or latency
  percentiles
- A bug happened 2 hours ago and you have zero trace of it
- You're alerting on "5xx response rate" but can't tell a bug from a client
  error from an upstream timeout

You need: persistent logs, queryable metrics, and alerts that actually fire
when things break.

## The 2026 observability stack

```text
Worker code
    ├── console.log()  →  Workers Logs (persistent, searchable, 3-92 day retention)
    ├── wrangler.toml [observability]  →  automatic request metrics
    ├── Analytics Engine  →  custom business metrics (latency, error types)
    └── Logpush  →  export everything to R2/S3/external SIEM for long-term storage
```

## Layer 1: Enable Workers Logs (persistent structured logs)

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[observability]
enabled = true
head_sampling_rate = 1  # 1.0 = log 100% of requests; 0.1 = 10% sampling
```

That's it. Workers Logs automatically captures:
- Request method, URL, status, duration
- `console.log()` / `console.error()` output
- Uncaught exceptions
- `fetch()` subrequests

View in dashboard: **Workers & Pages → your Worker → Logs**, or query via API:

```bash
# Query logs via wrangler (2026 syntax)
npx wrangler logs query --filter 'status >= 500' --since 1h
```

## Layer 2: Structured logging in code

Stop using `console.log("here")`. Use structured JSON:

```typescript
// src/logger.ts
export function log(level: string, message: string, data?: Record<string, unknown>) {
  console.log(JSON.stringify({
    level,
    message,
    timestamp: new Date().toISOString(),
    ...data,
  }));
}

// Usage in Worker
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const startTime = Date.now();
    const url = new URL(request.url);
    const requestId = crypto.randomUUID();

    log("info", "request.start", {
      requestId,
      method: request.method,
      path: url.pathname,
      userAgent: request.headers.get("user-agent"),
    });

    try {
      const response = await handleRequest(request, env);
      const duration = Date.now() - startTime;

      log("info", "request.end", {
        requestId,
        status: response.status,
        durationMs: duration,
      });

      return response;
    } catch (error) {
      const duration = Date.now() - startTime;
      log("error", "request.error", {
        requestId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
        durationMs: duration,
      });
      return new Response("Internal Server Error", { status: 500 });
    }
  },
};
```

Now you can query logs by field:

```bash
# Find all errors in the last hour
npx wrangler logs query --filter 'level=error' --since 1h

# Find slow requests (>1000ms)
npx wrangler logs query --filter 'durationMs > 1000' --since 24h
```

## Layer 3: Workers Analytics Engine (custom metrics)

Workers Logs are for individual events. Analytics Engine is for aggregated
metrics: "p99 latency by route", "error rate by version", "requests per second".

```toml
# wrangler.toml
[[analytics_engine_datasets]]
binding = "METRICS"
dataset = "my-worker-metrics"
```

```typescript
interface Env {
  METRICS: AnalyticsEngineDataset;
}

// Write custom metrics
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);

    try {
      const response = await handleRequest(request, env);
      const duration = Date.now() - start;

      // Log a metric data point
      // blob1 = index fields (high cardinality OK: route, status, version)
      // doubles = numeric values (duration)
      env.METRICS.writeDataPoint({
        blobs: [url.pathname, response.status.toString(), env.APP_VERSION || "unknown"],
        doubles: [duration],
        indexes: [request.cf?.colo as string || "unknown"],  // for grouping
      });

      return response;
    } catch (error) {
      env.METRICS.writeDataPoint({
        blobs: [url.pathname, "500", env.APP_VERSION || "unknown"],
        doubles: [Date.now() - start],
        indexes: [request.cf?.colo as string || "unknown"],
      });
      throw error;
    }
  },
};
```

Query metrics in the dashboard or via GraphQL API:

```sql
-- Average latency by route (SQL-style query via Analytics Engine API)
SELECT blob1 AS route,
       AVG(double1) AS avg_latency_ms,
       COUNT(*) AS request_count
FROM my_worker_metrics
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY blob1
ORDER BY avg_latency_ms DESC
```

## Layer 4: Logpush for long-term retention

Workers Logs retain 3-92 days. For compliance or long-term analysis, use
Logpush to ship logs to R2 or an external destination.

```bash
# Create a Logpush job to R2
npx wrangler logpush create \
  --destination r2://my-logs-bucket/workers/{DATE}/ \
  --dataset "my-worker" \
  "--output-type=json"
```

```toml
# Or configure in wrangler.toml (2026)
[[logpush_jobs]]
name = "worker-logs-to-r2"
dataset = "my-worker"
destination = "r2://my-logs-bucket/workers/{DATE}/"
output_type = "json"
```

## Gotchas

- **`head_sampling_rate` is the #1 observability footgun.** If you set it to
  `0.1` (10%), you will miss 90% of errors. For production debugging, keep it
  at `1` (100%). Only sample if you have extreme volume (>10M req/day) and
  cost concerns. Use Analytics Engine (aggregated) for the unsampled view.
- **`console.log()` is NOT free.** Each log line is a Workers Logs ingestion
  event. At scale (millions of requests with verbose logging), this costs real
  money. Log structured data, but be intentional about volume.
- **Analytics Engine has eventual consistency.** Data points are queryable
  within seconds to minutes, NOT real-time. Don't use it for real-time
  alerting — use Workers Logs + a webhook for that.
- **Analytics Engine blob fields have a 512-byte limit each.** Don't put full
  URLs or request bodies in blob fields — hash them or truncate. Use indexes
  (also limited) for low-cardinality grouping only.
- **`wrangler tail` is for dev only, not production monitoring.** It samples,
  disconnects, and loses history. It's fine for debugging a local deploy but
  will miss production issues. Use persistent Workers Logs.
- **Logpush adds latency to log availability.** Logs appear in R2 minutes to
  hours after the request. Don't use Logpush-fed data for real-time alerting.
- **Don't log secrets.** `console.log(env.API_KEY)` writes the value to
  persistent Workers Logs. Anyone with dashboard or API access to logs can
  read it. Redact or omit secrets entirely.
- **Custom metrics vs. automatic metrics.** The `[observability]` block gives
  you automatic request count/duration. Analytics Engine gives you custom
  dimensions (by route, by user type, by version). You need both for full
  visibility — neither covers the other's use case completely.

## Alerting pattern

Workers Logs + Analytics Engine don't have built-in alerting. Use a webhook
Worker:

```typescript
// alert-worker.ts — triggered by cron every minute
export default {
  async scheduled(event: ScheduledEvent, env: Env) {
    // Query Workers Logs for 5xx errors in the last minute
    const response = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.ACCOUNT_ID}/workers/logs/query`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
        body: JSON.stringify({
          queryId: "prod-worker",
          parameters: { since: "1m", filter: "status >= 500" },
        }),
      }
    );
    const data = await response.json();

    if (data.result?.length > 10) {
      // Threshold breached → alert
      await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        body: JSON.stringify({ text: `ALERT: ${data.result.length} 5xx errors in 1 min` }),
      });
    }
  },
};
```
