# Analytics Engine Write Throughput Batch Optimization

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Worker emitting one `writeDataPoint()` call per request drops data points silently
when request rates exceed 25 data points per second per Worker invocation, or when a Worker
invocation produces more than 20 data points. You see gaps in your Analytics Engine time-series
dashboards that do not correspond to actual traffic drops.

Alternatively, you have a fan-out Worker that aggregates events from multiple upstream sources and
needs to emit hundreds of data points per invocation without hitting rate limits.

## Context

Cloudflare Analytics Engine is a time-series write API built into the Workers runtime. Each
`env.ANALYTICS.writeDataPoint()` call is a fire-and-forget write — the Worker does not await it,
and no error is surfaced for dropped points. Limits as of 2024:

- Maximum **20 data points per Worker invocation**.
- Each data point supports up to **20 blob fields**, **20 double fields**, and **1 index field**.
- Writes are aggregated by Cloudflare before storage; the query API (Workers Analytics Engine
  SQL API) has a ~1-minute propagation delay.

When event volume exceeds 20 per invocation, you must either aggregate events into fewer data
points per invocation (pre-aggregate in memory) or fan out to multiple invocations via Queues.

The index field (a single string up to 32 bytes) is the primary partition key for SQL queries.
Cardinality of the index determines query scan cost; keep it low (e.g., datacenter ID, service
name) rather than high-cardinality values (e.g., user IDs).

## 1. Naive per-event write (hits the 20-point cap)

```typescript
// BAD: emits one data point per event — exceeds 20-point cap in high-traffic invocations
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const events: Event[] = await request.json();

    for (const event of events) {
      // Silently dropped after the 20th data point
      env.ANALYTICS.writeDataPoint({
        blobs: [event.type, event.userId],
        doubles: [event.durationMs, event.bytes],
        indexes: [event.service]
      });
    }

    return new Response("ok");
  }
};
```

## 2. Pre-aggregate events into bucketed data points

Reduce N events to ≤20 data points by grouping by a dimension (e.g., event type + service) and
summing numeric fields. This preserves aggregate statistics while staying within the limit.

```typescript
interface Event {
  type: string;
  service: string;
  durationMs: number;
  bytes: number;
  statusCode: number;
}

interface Bucket {
  count: number;
  totalDurationMs: number;
  totalBytes: number;
  errorCount: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const events: Event[] = await request.json();

    // Aggregate into at most (types × services) buckets
    const buckets = new Map<string, Bucket>();
    for (const event of events) {
      const key = `${event.service}:${event.type}`;
      const existing = buckets.get(key);
      if (existing) {
        existing.count++;
        existing.totalDurationMs += event.durationMs;
        existing.totalBytes += event.bytes;
        if (event.statusCode >= 500) existing.errorCount++;
      } else {
        buckets.set(key, {
          count: 1,
          totalDurationMs: event.durationMs,
          totalBytes: event.bytes,
          errorCount: event.statusCode >= 500 ? 1 : 0
        });
      }
    }

    // Emit one data point per bucket — guaranteed ≤20 if you control dimension cardinality
    let pointsEmitted = 0;
    for (const [key, bucket] of buckets) {
      if (pointsEmitted >= 20) break; // hard cap safety
      const [service, eventType] = key.split(":", 2);
      env.ANALYTICS.writeDataPoint({
        blobs: [eventType, String(bucket.count)],
        doubles: [
          bucket.count,
          bucket.totalDurationMs,
          bucket.totalBytes,
          bucket.errorCount,
          bucket.totalDurationMs / bucket.count  // avg latency
        ],
        indexes: [service.slice(0, 32)]
      });
      pointsEmitted++;
    }

    return new Response(JSON.stringify({ pointsEmitted, bucketsTotal: buckets.size }), {
      headers: { "content-type": "application/json" }
    });
  }
};
```

## 3. Queue-based fan-out for high-cardinality event streams

When event cardinality is inherently high (per-user events, per-request traces), use Workers
Queues to route events to an aggregator consumer that batches across multiple producer invocations.

```typescript
// Producer Worker — sends events to Queue without hitting Analytics Engine directly
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const event = await request.json<Event>();

    await env.EVENTS_QUEUE.send(event, { contentType: "json" });

    return new Response("queued", { status: 202 });
  }
};

// Consumer Worker — receives batches from Queue, aggregates, writes to Analytics Engine
export default {
  async queue(batch: MessageBatch<Event>, env: Env): Promise<void> {
    const buckets = new Map<string, Bucket>();

    for (const message of batch.messages) {
      const event = message.body;
      const key = `${event.service}:${event.type}`;
      const existing = buckets.get(key);
      if (existing) {
        existing.count++;
        existing.totalDurationMs += event.durationMs;
        existing.totalBytes += event.bytes;
      } else {
        buckets.set(key, {
          count: 1,
          totalDurationMs: event.durationMs,
          totalBytes: event.bytes,
          errorCount: 0
        });
      }
    }

    // Queues consumer can process up to 10,000 messages per batch
    // Emit one data point per unique dimension tuple (still capped at 20 per invocation)
    let i = 0;
    for (const [key, bucket] of buckets) {
      if (i >= 20) break;
      const [service, eventType] = key.split(":", 2);
      env.ANALYTICS.writeDataPoint({
        blobs: [eventType],
        doubles: [bucket.count, bucket.totalDurationMs, bucket.totalBytes],
        indexes: [service.slice(0, 32)]
      });
      i++;
    }

    batch.ackAll();
  }
};
```

## 4. Querying with the SQL API for aggregated time-series

```typescript
// Query the last 5 minutes of aggregated latency per service
async function queryLatency(env: Env): Promise<Response> {
  const sql = `
    SELECT
      index1 AS service,
      SUM(_sample_interval * double1) AS total_requests,
      SUM(_sample_interval * double2) / SUM(_sample_interval * double1) AS avg_latency_ms,
      toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS minute
    FROM analytics_dataset
    WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
    GROUP BY service, minute
    ORDER BY minute DESC
  `;

  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json"
      },
      body: sql
    }
  );

  return response;
}
```

## 5. Tracking write saturation with Server-Timing

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const events: Event[] = await request.json();
    const t0 = Date.now();

    let pointsWritten = 0;
    // ... aggregation logic ...
    pointsWritten = Math.min(buckets.size, 20);

    const processingMs = Date.now() - t0;
    const saturation = (pointsWritten / 20) * 100;

    return new Response("ok", {
      headers: {
        "server-timing":
          `ae-process;dur=${processingMs}, ae-saturation;dur=${saturation.toFixed(0)}`
      }
    });
  }
};
```

Monitor `ae-saturation` approaching 100 as a signal to introduce queue-based fan-out.

## Anti-patterns

- Emitting one data point per HTTP request in a high-traffic Worker — silently drops points once
  the 20-point-per-invocation cap is hit; no error, no retry.
- Using high-cardinality values as the `indexes` field (user IDs, request IDs) — causes
  full-scan performance degradation in SQL API queries; the index is a partition hint, not a
  unique key.
- Awaiting `writeDataPoint()` — the method is synchronous and fire-and-forget; awaiting it is a
  no-op and adds misleading ceremony.
- Storing raw events in KV or D1 as a workaround for the 20-point cap — these are higher-latency
  and higher-cost storage tiers for analytics write patterns.

## Gotchas

- The `_sample_interval` column in SQL queries is critical for accuracy: Analytics Engine uses
  adaptive sampling under load. Divide aggregated sums by `_sample_interval` to get true counts.
- Data points have a ~60-second minimum propagation delay before appearing in SQL queries.
  Do not use Analytics Engine for real-time alerting requiring sub-minute freshness.
- The `indexes` field is limited to 32 bytes. Longer strings are silently truncated.
- `blob` fields are limited to 256 bytes each; excess is silently dropped.
- Analytics Engine datasets are retention-limited (default 90 days); plan archival to R2 for
  longer-term storage.

## Verification

1. Deploy a test Worker that emits exactly 21 data points per invocation and query the SQL API
   after 2 minutes; observe that only 20 appear.
2. Use `wrangler tail` to confirm no JavaScript errors from `writeDataPoint()` even when
   the cap is exceeded (confirms silent-drop behavior).
3. Monitor `ae-saturation` via `Server-Timing` in Cloudflare Logpush over a 24-hour window.
4. Query `SELECT COUNT() FROM analytics_dataset WHERE timestamp >= NOW() - INTERVAL '5' MINUTE`
   and compare to actual request count from Workers metrics.

## Related

- `queues-throughput-batching.md`
- `analytics-engine-rum-web-vitals.md`
- `durable-objects-alarm-write-coalescing.md`
- `workers-queues-background-offload.md`

## Sources

- Analytics Engine limits: https://developers.cloudflare.com/analytics/analytics-engine/limits/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Analytics Engine workers binding: https://developers.cloudflare.com/analytics/analytics-engine/get-started/
- Adaptive sampling docs: https://developers.cloudflare.com/analytics/analytics-engine/sampling/
