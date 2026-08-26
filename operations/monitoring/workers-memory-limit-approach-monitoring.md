# Workers Memory Limit Approach Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Cloudflare Workers hit the 128 MB memory limit and are killed with an `exceeded-memory`
outcome, but you only discover this after user-facing errors appear. You need early warning when
a Worker's in-request heap is approaching the limit so you can profile and reduce allocations
before the limit is breached in production.

## Context
Cloudflare Workers enforce a hard 128 MB heap limit per isolate. The Workers runtime exposes
`performance.memory` (a non-standard V8 extension) inside the Worker fetch handler, giving you
`usedJSHeapSize` and `totalJSHeapSize` at the point of sampling. A Tail Worker captures the
`exceeded-memory` outcome and can be combined with in-handler sampling to build a
memory-headroom distribution in Analytics Engine for trend analysis.

---

## Section 1 — In-Handler Memory Sampling

Sample `performance.memory` inside the fetch handler and attach it to a structured log that the
Tail Worker will pick up. Sample only a fraction of requests to avoid overhead on
memory-intensive handlers.

```typescript
// my-worker.ts
export interface Env {
  MEMORY_SAMPLE_RATE: string; // "0.01" = 1% of requests
}

declare const performance: {
  memory?: {
    usedJSHeapSize: number;
    totalJSHeapSize: number;
    jsHeapSizeLimit: number;
  };
};

const HEAP_LIMIT_BYTES = 128 * 1024 * 1024; // 128 MB

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const sampleRate = parseFloat(env.MEMORY_SAMPLE_RATE ?? "0.01");
    const shouldSample = Math.random() < sampleRate;

    let response: Response;

    try {
      response = await handleRequest(request, env);
    } finally {
      // Only sample when opted-in AND memory API is available (V8-based isolate)
      if (shouldSample && performance.memory) {
        const { usedJSHeapSize, totalJSHeapSize, jsHeapSizeLimit } =
          performance.memory;

        const headroomBytes = (jsHeapSizeLimit || HEAP_LIMIT_BYTES) - usedJSHeapSize;
        const usedPct = (usedJSHeapSize / (jsHeapSizeLimit || HEAP_LIMIT_BYTES)) * 100;

        // Emit structured log for the Tail Worker to forward to Analytics Engine
        console.log(
          JSON.stringify({
            _type: "memory_sample",
            usedBytes: usedJSHeapSize,
            totalBytes: totalJSHeapSize,
            limitBytes: jsHeapSizeLimit || HEAP_LIMIT_BYTES,
            headroomBytes,
            usedPct: Math.round(usedPct * 10) / 10,
            route: new URL(request.url).pathname.split("/")[1] ?? "root",
          })
        );

        // Hard warning: if we're over 80%, log at warn level too
        if (usedPct > 80) {
          console.warn(
            `[memory] approaching limit: used=${(usedJSHeapSize / 1024 / 1024).toFixed(1)}MB ` +
              `(${usedPct.toFixed(1)}%) headroom=${(headroomBytes / 1024 / 1024).toFixed(1)}MB`
          );
        }
      }
    }

    return response!;
  },
} satisfies ExportedHandler<Env>;

async function handleRequest(request: Request, _env: Env): Promise<Response> {
  // ... actual business logic ...
  return new Response("OK");
}
```

---

## Section 2 — Tail Worker: Forwarding to Analytics Engine and Capturing `exceeded-memory`

```typescript
// memory-tail-worker.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  ALERT_WEBHOOK_URL: string;
}

interface MemorySampleLog {
  _type: "memory_sample";
  usedBytes: number;
  totalBytes: number;
  limitBytes: number;
  headroomBytes: number;
  usedPct: number;
  route: string;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    const alertMessages: string[] = [];

    for (const event of events) {
      const workerName = event.scriptName ?? "unknown";

      // 1. Capture exceeded-memory kills directly from Tail outcome
      if (event.outcome === "exceeded-memory") {
        env.ANALYTICS.writeDataPoint({
          blobs: [workerName, "exceeded", ""],
          doubles: [128, 100, 0], // at limit: used=128MB, pct=100, headroom=0
          indexes: [workerName],
        });

        alertMessages.push(
          `[OOM KILL] ${workerName} exceeded 128MB memory limit at ${new Date(event.eventTimestamp).toISOString()}`
        );
        continue;
      }

      // 2. Parse structured memory sample logs from in-handler sampling
      for (const log of event.logs) {
        const raw = log.message[0];
        if (typeof raw !== "string") continue;

        let entry: MemorySampleLog;
        try {
          entry = JSON.parse(raw) as MemorySampleLog;
        } catch {
          continue;
        }

        if (entry._type !== "memory_sample") continue;

        const usedMB = entry.usedBytes / 1024 / 1024;
        const headroomMB = entry.headroomBytes / 1024 / 1024;

        env.ANALYTICS.writeDataPoint({
          blobs: [
            workerName,                              // blob1: worker script name
            event.outcome,                           // blob2: request outcome
            entry.route,                             // blob3: route prefix
          ],
          doubles: [
            usedMB,                                  // double1: used heap in MB
            entry.usedPct,                           // double2: % of limit used
            headroomMB,                              // double3: headroom in MB
          ],
          indexes: [workerName],
        });

        // Alert if headroom drops below 20 MB
        if (headroomMB < 20) {
          alertMessages.push(
            `[MEM WARNING] ${workerName} route=/${entry.route} ` +
              `used=${usedMB.toFixed(1)}MB (${entry.usedPct}%) headroom=${headroomMB.toFixed(1)}MB`
          );
        }
      }
    }

    if (alertMessages.length > 0) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: alertMessages.join("\n") }),
      }).catch(() => {
        // Best-effort; do not rethrow in Tail Worker
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Analytics Engine SQL: Memory Headroom Queries

```sql
-- P95 / P99 heap usage per worker and route (last hour)
SELECT
  blob1                                       AS worker_name,
  blob3                                       AS route,
  quantileWeighted(0.50)(double1, 1)          AS p50_used_mb,
  quantileWeighted(0.95)(double1, 1)          AS p95_used_mb,
  quantileWeighted(0.99)(double1, 1)          AS p99_used_mb,
  min(double3)                                AS min_headroom_mb,
  count()                                     AS sample_count
FROM workers_analytics.memory_samples         -- dataset name from wrangler.toml
WHERE timestamp > now() - INTERVAL '1' HOUR
GROUP BY blob1, blob3
ORDER BY p99_used_mb DESC;
```

```sql
-- Count of exceeded-memory kill events in the last 24 hours
SELECT
  blob1                        AS worker_name,
  countIf(blob2 = 'exceeded')  AS oom_kills,
  countIf(double2 > 80)        AS high_usage_samples,
  count()                      AS total_samples
FROM workers_analytics.memory_samples
WHERE timestamp > now() - INTERVAL '24' HOUR
GROUP BY blob1
ORDER BY oom_kills DESC;
```

```sql
-- Memory usage trend: hourly P95 over the last 7 days
SELECT
  toStartOfHour(timestamp)              AS hour,
  blob1                                 AS worker_name,
  quantileWeighted(0.95)(double1, 1)   AS p95_used_mb,
  min(double3)                          AS min_headroom_mb
FROM workers_analytics.memory_samples
WHERE timestamp > now() - INTERVAL '7' DAY
  AND blob2 != 'exceeded'
GROUP BY hour, blob1
ORDER BY hour ASC;
```

---

## Anti-patterns
- Calling `performance.memory` on every request — the sampling overhead is low but non-zero;
  use a sample rate of 1–5% in high-traffic Workers to limit log volume.
- Treating `totalJSHeapSize` as the hard limit — V8 reports total committed heap, which can
  be lower than `jsHeapSizeLimit`; always compare `usedJSHeapSize` against `jsHeapSizeLimit`.
- Logging memory stats at `console.error` — the Tail Worker cannot distinguish between
  application errors and memory telemetry by severity; use a structured JSON log with a
  `_type` discriminator (see Section 1).
- Using the Dashboard's memory metric alone — the Cloudflare dashboard shows aggregate memory
  per route only when `exceeded-memory` events occur; it does not show the distribution of
  near-limit usage on requests that succeeded.

## Gotchas
- `performance.memory` is not part of the Web Workers spec; it is a V8 extension available
  in Chrome/Node and Cloudflare Workers but not guaranteed forever — wrap the access in
  `if (performance.memory)` to avoid TypeScript errors and runtime exceptions.
- Durable Objects have a separate 128 MB limit per instance, not per request; the
  `performance.memory` API inside a DO handler reflects the DO's isolate heap, not the
  calling Worker's heap.
- Memory sampled at the *end* of a request reflects post-GC state; peak in-request usage
  may be higher. For request-allocating code (large JSON parsing, image processing), sample
  *before* the main allocation and again after if you need the delta.
- The `exceeded-memory` Tail outcome is reported as the request outcome; you will not receive
  logs emitted by `console.log` inside a request that was killed mid-execution.

## Verification
```bash
# Watch Tail Worker output filtered to memory events
wrangler tail memory-tail-worker --format json | jq 'select(.logs[].message[0] | contains("memory_sample"))'

# Confirm Analytics Engine is receiving memory data points
curl "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  --data-urlencode "query=SELECT blob1, max(double1) as max_mb, count() as samples FROM workers_analytics.memory_samples WHERE timestamp > now() - INTERVAL '5' MINUTE GROUP BY blob1"

# Simulate a near-OOM condition locally using wrangler dev
# Allocate large buffers in a test endpoint and observe console.warn output
wrangler dev my-worker --local
```

## Related
- `workers-memory-heap-snapshot-tail-worker.md`
- `durable-objects-memory-tail-workers.md`
- `worker-cpu-monitoring.md`
- `workers-cpu-time-percentile-analytics-engine.md`
- `tail-worker-structured-log-sampling-strategies.md`
- `analytics-engine-write-limits-and-backpressure.md`

## Sources
- https://developers.cloudflare.com/workers/platform/limits/#worker-limits
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developer.mozilla.org/en-US/docs/Web/API/Performance/memory
- https://developers.cloudflare.com/workers/runtime-apis/performance/
