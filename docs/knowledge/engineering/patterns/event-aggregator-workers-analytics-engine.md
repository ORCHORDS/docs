# Event Aggregator with Workers Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to track domain events (page views, checkout steps, API calls, feature usage)
at high volume from Workers without blowing past D1 write limits or KV rate limits.
You want real-time queryable aggregates via SQL, not just raw logs shipped to an
external analytics vendor.

## Context

Cloudflare Analytics Engine provides a write-optimized time-series store accessible
from Workers. Each Worker can emit `writeDataPoint()` calls up to 25 writes/request,
and Analytics Engine persists blobs that you query later via the Workers Analytics
Engine GraphQL API or the SQL API. It is ideal for event aggregation at the edge
where individual event cardinality is high but the aggregation occurs in the query
layer, not at write time.

This pattern treats Analytics Engine as the event sink for domain events: the Worker
converts every meaningful user action into a structured data point and writes it
immediately, keeping the hot path synchronous and cheap. Downstream dashboards and
SLO monitors run periodic queries against the SQL endpoint.

---

## Domain Event Schema Design

Design data points around query patterns, not raw event shapes. Analytics Engine
supports up to 20 double (numeric) fields, 20 blob (string) fields, and one index
field per data point. Reserve the index for the highest-cardinality dimension you
filter on most (typically `tenant_id` or `user_id`).

```typescript
// types/analytics.ts
export interface DomainEventPoint {
  // index field — primary filter dimension
  tenantId: string;

  // blob fields — categorical dimensions
  eventType: string;   // "checkout.started" | "api.called" | "feature.used"
  resourceId: string;
  userId: string;
  region: string;
  planTier: string;

  // double fields — numeric measurements
  durationMs: number;
  retryCount: number;
  payloadBytes: number;
  statusCode: number;
}

export type CheckoutEvent = {
  type: "checkout.started" | "checkout.completed" | "checkout.abandoned";
  tenantId: string;
  userId: string;
  cartValueCents: number;
  itemCount: number;
  durationMs: number;
};
```

## Writing Data Points from a Worker

```typescript
// src/analytics.ts
import { Env } from "./types";
import { DomainEventPoint, CheckoutEvent } from "./analytics";

export function emitCheckoutEvent(
  env: Env,
  event: CheckoutEvent,
  request: Request
): void {
  // writeDataPoint is non-blocking and fire-and-forget
  env.ANALYTICS.writeDataPoint({
    indexes: [event.tenantId],
    blobs: [
      event.type,           // blob1: eventType
      event.userId,         // blob2: userId
      "",                   // blob3: resourceId (unused here)
      request.cf?.region ?? "unknown",  // blob4: region
      "",                   // blob5: planTier (populated by lookup below)
    ],
    doubles: [
      event.cartValueCents, // double1: cartValueCents
      event.itemCount,      // double2: itemCount
      event.durationMs,     // double3: durationMs
      0,                    // double4: retryCount
      0,                    // double5: statusCode
    ],
  });
}

// src/worker.ts
import { Env } from "./types";
import { emitCheckoutEvent } from "./analytics";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/checkout/start" && request.method === "POST") {
      const body = await request.json<{ tenantId: string; userId: string; cartValueCents: number; itemCount: number }>();
      const start = Date.now();

      // ... business logic ...
      const result = await processCheckout(body, env);

      emitCheckoutEvent(env, {
        type: "checkout.started",
        tenantId: body.tenantId,
        userId: body.userId,
        cartValueCents: body.cartValueCents,
        itemCount: body.itemCount,
        durationMs: Date.now() - start,
      }, request);

      return Response.json(result);
    }

    return new Response("Not found", { status: 404 });
  },
};

async function processCheckout(body: any, env: Env): Promise<object> {
  // placeholder for real business logic
  return { orderId: crypto.randomUUID() };
}
```

## Querying Aggregates via SQL API

Analytics Engine exposes a SQL-compatible endpoint. Query it from a scheduled Worker
or an admin API to generate rollups, SLO reports, or feed dashboards.

```typescript
// src/analytics-query.ts
const ACCOUNT_ID = "<YOUR_ACCOUNT_ID>";
const AE_DATASET  = "example_events";

interface AggRow {
  event_type: string;
  event_count: number;
  avg_duration_ms: number;
  p95_cart_value: number;
}

export async function fetchCheckoutFunnel(
  apiToken: string,
  tenantId: string,
  windowHours = 24
): Promise<AggRow[]> {
  const sql = `
    SELECT
      blob1                          AS event_type,
      COUNT()                        AS event_count,
      AVG(double3)                   AS avg_duration_ms,
      QUANTILE(0.95)(double1)        AS p95_cart_value
    FROM ${AE_DATASET}
    WHERE
      index1       = '${tenantId}'
      AND blob1   LIKE 'checkout.%'
      AND timestamp > NOW() - INTERVAL '${windowHours}' HOUR
    GROUP BY blob1
    ORDER BY event_count DESC
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!res.ok) {
    throw new Error(`Analytics Engine query failed: ${res.status} ${await res.text()}`);
  }

  const { data } = await res.json<{ data: AggRow[] }>();
  return data;
}

// Scheduled Worker — runs hourly to update KV cache with funnel metrics
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const tenants = await env.DB.prepare("SELECT id FROM tenants WHERE active = 1").all();

    for (const tenant of tenants.results) {
      const rows = await fetchCheckoutFunnel(env.CF_API_TOKEN, tenant.id as string);
      await env.METRICS_KV.put(
        `funnel:${tenant.id}`,
        JSON.stringify({ rows, updatedAt: Date.now() }),
        { expirationTtl: 7200 }
      );
    }
  },
};
```

## Batching Multiple Events per Request

When a single request triggers multiple events (e.g., a bulk import), batch calls
to stay within the 25-writes-per-request limit and avoid silent drops.

```typescript
// src/batch-emit.ts
export class EventAggregator {
  private queue: Array<AnalyticsEngineDataPoint> = [];
  private readonly limit = 25;

  constructor(private readonly sink: AnalyticsEngineDataset) {}

  push(point: AnalyticsEngineDataPoint): void {
    if (this.queue.length >= this.limit) {
      console.warn("EventAggregator: per-request write limit reached; dropping event");
      return;
    }
    this.queue.push(point);
  }

  flush(): void {
    for (const point of this.queue) {
      this.sink.writeDataPoint(point);
    }
    this.queue = [];
  }
}

// usage in handler
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const agg = new EventAggregator(env.ANALYTICS);

    const items = await request.json<Array<{ id: string; value: number }>>();
    for (const item of items) {
      agg.push({
        indexes: [item.id],
        blobs: ["import.item.processed"],
        doubles: [item.value],
      });
    }

    const result = await processItems(items, env);
    agg.flush(); // write all points before returning
    return Response.json(result);
  },
};

async function processItems(items: Array<{ id: string; value: number }>, env: Env): Promise<object> {
  return { processed: items.length };
}
```

## Anti-patterns

- **Writing raw request logs**: Analytics Engine is not a log store. Write semantic
  domain events, not HTTP access logs — use Logpush for that.
- **Using KV or D1 as a counter for every event**: D1 write throughput is limited;
  incrementing a counter row per event causes contention at scale. Let AE aggregate.
- **Querying Analytics Engine on the hot path**: SQL queries against AE are expensive
  and unsuitable for request-time execution. Pre-compute metrics on a schedule.
- **Exceeding 25 writes per request**: Silent drops with no error. Always count and cap.
- **Storing PII in blobs**: Analytics Engine data is retained and queryable; avoid
  names, emails, or tokens. Use opaque IDs and resolve them at query time from D1.

## Gotchas

- `writeDataPoint()` is fire-and-forget; failures do not surface as exceptions. Add
  a wrapper that counts emissions and validates before calling to detect misconfiguration.
- The `index1` field is limited to 96 bytes. Truncate or hash long tenant IDs.
- Analytics Engine SQL API requires a Cloudflare API token with the
  `Account Analytics: Read` permission — not a Workers-specific token.
- There is a ~30-second ingestion delay before data points are queryable.
- Double fields are IEEE 754 doubles; store monetary values in integer cents to avoid
  floating-point precision loss during aggregation.

## Verification

```bash
# verify data points are arriving
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT COUNT() AS n FROM example_events WHERE timestamp > NOW() - INTERVAL '"'"'5'"'"' MINUTE"}'

# expected: {"data":[{"n":42}],...}
```

Run an integration test that posts to the Worker, waits 60 seconds, then queries
AE and asserts `n > 0` for the emitted event type.

## Related

- `outbox-pattern-d1-reliable-publishing.md` — guarantee event emission via D1 outbox
- `observer-pattern-workers-durable-objects-event-bus.md` — in-process event bus
- `fan-out-queues-workers.md` — distributing events to downstream consumers
- `structured-logging-detail.md` — logging vs. metrics separation

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/binding/
- https://developers.cloudflare.com/analytics/analytics-engine/limits/
