# Workers Response Size Distribution Monitoring

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Bandwidth costs rise unexpectedly, or mobile clients report slow page loads despite good p99 TTFB.
The common root cause is response bloat: a serialization change, an ORM adding extra fields, or
a caching middleware that stopped compressing. Standard Workers analytics surface request count and
error rate but not response size distribution. Without p50/p95/p99 size percentiles broken down
by route, detecting and attributing bloat requires manual log parsing. This article sets up
response size distribution monitoring using Tail Workers and Analytics Engine.

## Context

`Content-Length` headers are the most reliable source of response size, but they are absent for
chunked or streaming responses. A Tail Worker receives the finalized response metadata including
`event.response.headers` (where available) and can measure actual compressed/uncompressed size.
For streaming responses, record the size in your primary Worker using a `TransformStream` byte
counter, then attach it as a custom header that the Tail Worker can read. Analytics Engine's
`quantileWeighted` function gives you real percentiles over the distribution without requiring a
histogram backend.

## Recording Response Size in the Primary Worker

```typescript
// src/size-tracking-middleware.ts
export function withSizeTracking(
  handler: (req: Request, env: Env, ctx: ExecutionContext) => Promise<Response>
) {
  return async (request: Request, env: Env, ctx: ExecutionContext): Promise<Response> => {
    const response = await handler(request, env, ctx);

    // For non-streaming responses, clone and measure
    if (!response.body || response.headers.get("transfer-encoding") === "chunked") {
      // Streaming: use TransformStream counter
      let byteCount = 0;
      const { readable, writable } = new TransformStream({
        transform(chunk, controller) {
          byteCount += chunk.byteLength;
          controller.enqueue(chunk);
        },
        flush(controller) {
          controller.terminate();
        },
      });

      // Pipe response body through counter
      response.body!.pipeTo(writable);

      const tracked = new Response(readable, response);
      tracked.headers.set("X-Response-Bytes", "streaming"); // filled post-flush; use Tail Worker heuristic
      return tracked;
    }

    // For buffered responses — clone to read size without consuming
    const clone = response.clone();
    const buf = await clone.arrayBuffer();
    const sizeBytes = buf.byteLength;

    const out = new Response(response.body, response);
    out.headers.set("X-Response-Bytes", String(sizeBytes));
    out.headers.set("X-Route", extractRoute(request.url)); // e.g., "/api/products"
    return out;
  };
}

function extractRoute(url: string): string {
  const path = new URL(url).pathname;
  // Normalize dynamic segments: /api/users/123 → /api/users/:id
  return path.replace(/\/[0-9a-f-]{8,}/gi, "/:id").replace(/\/\d+/g, "/:id");
}
```

## Tail Worker: Write Size Distribution to Analytics Engine

```typescript
// tail-size-worker/src/index.ts
export interface Env {
  SIZE_DIST: AnalyticsEngineDataset;
}

interface TailEvent {
  scriptName: string;
  outcome: string;
  event: {
    request: { url: string; method: string };
    response?: { status: number; headers?: Record<string, string> };
    wallTime: number;
    cpuTime: number;
  };
  eventTimestamp: number;
}

export default {
  async tail(events: TailEvent[], env: Env): Promise<void> {
    for (const item of events) {
      const headers = item.event.response?.headers ?? {};
      const sizeRaw = headers["x-response-bytes"] ?? headers["content-length"] ?? "0";
      const sizeBytes = sizeRaw === "streaming" ? -1 : Number(sizeRaw);
      const route = headers["x-route"] ?? extractRoute(item.event.request?.url ?? "");
      const status = String(item.event.response?.status ?? 0);
      const method = item.event.request?.method ?? "GET";

      // Skip unknown sizes for percentile accuracy
      if (sizeBytes < 0) continue;

      env.SIZE_DIST.writeDataPoint({
        blobs: [
          item.scriptName ?? "unknown", // blob1 – script
          route,                         // blob2 – normalized route
          method,                        // blob3 – HTTP method
          status,                        // blob4 – status code
        ],
        doubles: [
          sizeBytes,                     // double1 – response bytes
          item.event.wallTime,           // double2 – wall time ms
          sizeBytes / Math.max(item.event.wallTime, 1), // double3 – bytes/ms throughput
          1,                             // double4 – request count
        ],
        indexes: [route],
      });
    }
  },
} satisfies ExportedHandler<Env>;

function extractRoute(url: string): string {
  try {
    const path = new URL(url).pathname;
    return path.replace(/\/[0-9a-f-]{8,}/gi, "/:id").replace(/\/\d+/g, "/:id");
  } catch {
    return "unknown";
  }
}
```

## Percentile Query per Route

```sql
SELECT
  blob2 AS route,
  count() AS requests,
  quantileWeighted(0.50)(double1, 1) AS p50_bytes,
  quantileWeighted(0.90)(double1, 1) AS p90_bytes,
  quantileWeighted(0.95)(double1, 1) AS p95_bytes,
  quantileWeighted(0.99)(double1, 1) AS p99_bytes,
  max(double1) AS max_bytes,
  avg(double1) AS avg_bytes
FROM workers_response_size
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY blob2
ORDER BY p99_bytes DESC
LIMIT 25
```

## Week-over-Week Size Regression Detection

```typescript
// src/size-regression-check.ts
async function detectSizeRegression(env: Env, route: string): Promise<void> {
  const [current, prior] = await Promise.all([
    queryP99(env, route, "1 HOUR"),
    queryP99(env, route, "1 HOUR", "7 DAY"), // same hour last week
  ]);

  const changeRatio = current / Math.max(prior, 1);
  if (changeRatio > 1.25) {
    await env.ALERT_QUEUE.send({
      severity: "warning",
      title: `Response size regression on ${route}`,
      message: `p99 size grew ${((changeRatio - 1) * 100).toFixed(1)}% vs last week: ${prior}B → ${current}B`,
      runbook: "https://wiki.example.com/runbooks/response-size-regression",
    });
  }
}

async function queryP99(
  env: Env,
  route: string,
  window: string,
  offset = "0 SECOND"
): Promise<number> {
  const sql = `
    SELECT quantileWeighted(0.99)(double1, 1) AS p99
    FROM workers_response_size
    WHERE
      blob2 = '${route}'
      AND timestamp > NOW() - INTERVAL '${offset}' - INTERVAL '${window}'
      AND timestamp < NOW() - INTERVAL '${offset}'
  `;
  const res = await queryAE(sql, env);
  return Number(res.data?.[0]?.p99 ?? 0);
}
```

## Bandwidth Attribution by Route

```sql
SELECT
  blob2 AS route,
  sum(double1) AS total_bytes,
  sum(double1) / 1048576.0 AS total_mb,
  count() AS requests,
  avg(double1) AS avg_bytes_per_request
FROM workers_response_size
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY blob2
ORDER BY total_bytes DESC
LIMIT 20
```

## Alerting on Abnormally Large Responses

```typescript
// src/large-response-alert.ts – scheduled every 15 min
export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT blob2 AS route, max(double1) AS max_bytes, count() AS oversized_count
      FROM workers_response_size
      WHERE
        timestamp > NOW() - INTERVAL '15' MINUTE
        AND double1 > 5242880  -- 5 MB threshold
      GROUP BY blob2
    `;
    const res = await queryAE(sql, env);
    for (const row of (res.data ?? [])) {
      await env.ALERT_QUEUE.send({
        severity: "high",
        title: `Oversized responses on ${row.route}`,
        message: `${row.oversized_count} responses over 5 MB (max: ${(row.max_bytes / 1048576).toFixed(1)} MB)`,
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- **Using `Content-Length` alone for percentiles on compressed responses.** The header reflects
  compressed size; your application-level p99 should measure uncompressed payload size to detect
  data model changes. Track both when compression is in play.
- **Sampling only p99.** A compression bug might shrink p99 (truncated payloads) while bloating
  mean and p50. Always collect all three quantiles.
- **Writing one row per byte range bucket.** Analytics Engine supports `quantileWeighted` natively.
  Client-side bucketing wastes rows and loses resolution.
- **Including binary/media endpoints in the distribution.** Image or video routes skew the p99
  dramatically. Filter to `blob3 = 'GET'` and API routes (e.g., `blob2 LIKE '/api/%'`) for
  meaningful application-layer size tracking.

## Gotchas

- Response headers set with `out.headers.set(...)` after the body is piped are not guaranteed to
  appear in Tail Worker events for streaming responses. Use the `ctx.waitUntil` + KV pattern to
  pass the final byte count asynchronously if your responses are streaming.
- `Content-Length` is stripped by Cloudflare's edge for responses using `Transfer-Encoding:
  chunked`. Rely on `X-Response-Bytes` set by your Worker instead.
- Analytics Engine `quantileWeighted` is approximate (t-digest); expect ±1-2% error at p99.
- Response sizes from Cloudflare Cache HIT requests do not pass through your Worker, so
  `Content-Length` readings from the Tail Worker will be missing for cached assets. Filter by
  `blob4 != '304'` and note that cache misses are the only measurable surface.

## Verification

1. Deploy the primary Worker with size-tracking middleware and the Tail Worker.
2. Make 50 requests to a JSON API route; measure expected response size locally (e.g., 1,200 B).
3. Query:
   ```sql
   SELECT blob2, quantileWeighted(0.50)(double1, 1) AS p50
   FROM workers_response_size
   WHERE timestamp > NOW() - INTERVAL '5' MINUTE
   GROUP BY blob2
   ```
   Expect p50 close to 1,200.
4. Add a large unused field to the JSON response (inflate to ~5 kB) and redeploy.
5. Re-query; confirm p50 jumps and the regression alert fires.

## Related

- `tail-worker-cold-start-attribution.md`
- `workers-tail-real-time-log-streaming.md`
- `worker-cpu-monitoring.md`
- `workers-cpu-time-percentile-analytics-engine.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `observability-cost-control.md`

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
- https://developers.cloudflare.com/workers/runtime-apis/response/
