# End-to-End Request Tracing with Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple Cloudflare Workers communicating via service bindings and need to correlate logs and timing across all hops of a single request. Without a shared trace identifier it is impossible to reconstruct which downstream calls belonged to the same originating request or to measure cumulative latency.

---

## Context

Cloudflare Analytics Engine accepts arbitrary numeric and string blobs per data point, making it a natural fit for distributed tracing without an external backend. Each Worker in the call graph generates a span, attaches a shared `traceId`, and writes the span to Analytics Engine. The `traceId` is created with `crypto.randomUUID()` at the entry Worker and forwarded via the `X-Trace-Id` header through every service binding call. Downstream Workers read the header, create child spans, and write their own data points. A single SQL query against the Analytics Engine HTTP API reconstructs the full trace by filtering on `blob1 = ?`.

---

## Section 1 — wrangler.toml

```toml
name = "gateway-worker"
main = "src/gateway.ts"
compatibility_date = "2025-01-01"

[[analytics_engine_datasets]]
binding = "TRACES"
dataset = "request_traces"

[[services]]
binding = "AUTH_SERVICE"
service = "auth-worker"

[[services]]
binding = "DATA_SERVICE"
service = "data-worker"
```

---

## Section 2 — Gateway Worker (entry point)

```typescript
// src/gateway.ts
export interface Env {
  TRACES: AnalyticsEngineDataset;
  AUTH_SERVICE: Fetcher;
  DATA_SERVICE: Fetcher;
}

interface Span {
  traceId: string;
  spanId: string;
  parentSpanId: string | null;
  service: string;
  operation: string;
  startTime: number;
  status: number;
  durationMs: number;
}

function writeSpan(dataset: AnalyticsEngineDataset, span: Span): void {
  dataset.writeDataPoint({
    blobs: [
      span.traceId,       // blob1 — used for WHERE blob1 = ? queries
      span.spanId,        // blob2
      span.parentSpanId ?? "", // blob3
      span.service,       // blob4
      span.operation,     // blob5
    ],
    doubles: [
      span.durationMs,    // double1
      span.status,        // double2 — HTTP status code as number
      span.startTime,     // double3 — epoch ms
    ],
    indexes: [span.traceId], // enables efficient single-trace lookups
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const traceId = request.headers.get("X-Trace-Id") ?? crypto.randomUUID();
    const spanId = crypto.randomUUID();
    const gatewayStart = Date.now();

    // --- call auth service ---
    const authSpanId = crypto.randomUUID();
    const authStart = Date.now();
    const authResponse = await env.AUTH_SERVICE.fetch(
      new Request(request.url, {
        method: request.method,
        headers: {
          ...Object.fromEntries(request.headers),
          "X-Trace-Id": traceId,
          "X-Parent-Span-Id": spanId,
          "X-Span-Id": authSpanId,
        },
      })
    );
    const authDuration = Date.now() - authStart;

    writeSpan(env.TRACES, {
      traceId,
      spanId: authSpanId,
      parentSpanId: spanId,
      service: "auth-worker",
      operation: "authenticate",
      startTime: authStart,
      status: authResponse.status,
      durationMs: authDuration,
    });

    if (!authResponse.ok) {
      const gatewayDuration = Date.now() - gatewayStart;
      writeSpan(env.TRACES, {
        traceId,
        spanId,
        parentSpanId: null,
        service: "gateway-worker",
        operation: "handle_request",
        startTime: gatewayStart,
        status: 401,
        durationMs: gatewayDuration,
      });
      return new Response("Unauthorized", { status: 401 });
    }

    // --- call data service ---
    const dataSpanId = crypto.randomUUID();
    const dataStart = Date.now();
    const dataResponse = await env.DATA_SERVICE.fetch(
      new Request(request.url, {
        method: request.method,
        headers: {
          ...Object.fromEntries(request.headers),
          "X-Trace-Id": traceId,
          "X-Parent-Span-Id": spanId,
          "X-Span-Id": dataSpanId,
        },
      })
    );
    const dataDuration = Date.now() - dataStart;

    writeSpan(env.TRACES, {
      traceId,
      spanId: dataSpanId,
      parentSpanId: spanId,
      service: "data-worker",
      operation: "fetch_data",
      startTime: dataStart,
      status: dataResponse.status,
      durationMs: dataDuration,
    });

    const gatewayDuration = Date.now() - gatewayStart;
    writeSpan(env.TRACES, {
      traceId,
      spanId,
      parentSpanId: null,
      service: "gateway-worker",
      operation: "handle_request",
      startTime: gatewayStart,
      status: dataResponse.status,
      durationMs: gatewayDuration,
    });

    return new Response(await dataResponse.text(), {
      status: dataResponse.status,
      headers: { "X-Trace-Id": traceId },
    });
  },
};
```

---

## Section 3 — Querying a Full Trace

```typescript
// src/trace-query.ts — run from a debug Worker or local script
// Requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN env vars

const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const DATASET = "request_traces";

export async function getTrace(traceId: string): Promise<void> {
  // Analytics Engine SQL API — available at /v4/accounts/{id}/analytics_engine/sql
  const sql = `
    SELECT
      blob1 AS trace_id,
      blob2 AS span_id,
      blob3 AS parent_span_id,
      blob4 AS service,
      blob5 AS operation,
      double1 AS duration_ms,
      double2 AS status_code,
      double3 AS start_time_epoch_ms,
      timestamp
    FROM ${DATASET}
    WHERE blob1 = '${traceId}'
    ORDER BY double3 ASC
    LIMIT 200
  `;

  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!response.ok) {
    throw new Error(`Analytics Engine query failed: ${await response.text()}`);
  }

  const data = await response.json<{ data: Record<string, unknown>[] }>();
  console.table(data.data);
}

// Example: getTrace("550e8400-e29b-41d4-a716-446655440000");
```

---

## Anti-patterns

- **Generating a new traceId per service** — Each service binding must forward the same `traceId` received from its caller; generating a fresh UUID per hop breaks trace correlation entirely.
- **Writing spans synchronously before returning** — `writeDataPoint` is non-blocking; wrapping it in `await` is unnecessary and adds artificial latency. Call it fire-and-forget.
- **Using only blobs for filtering without indexes** — Always populate the `indexes` field with `traceId`; Analytics Engine uses it for efficient shard-level filtering, dramatically reducing query scan cost.
- **Storing high-cardinality data in doubles** — Doubles are 64-bit floats; UUIDs must go in blobs. Attempting to store a UUID as a number silently truncates it.

---

## Gotchas

- Analytics Engine data points are batched and may not appear in the SQL API for up to 60 seconds after writing; do not rely on them for real-time alerting in the same request cycle.
- The `indexes` field accepts a single value per data point. Use `traceId` as the index because it is the most selective filter in trace queries.
- Service binding requests do not automatically propagate headers; you must explicitly copy `X-Trace-Id` into every outbound `Request` object.
- The Analytics Engine SQL API has a default limit of 10,000 rows per query response; a very chatty trace with hundreds of spans may require pagination.
- `crypto.randomUUID()` is available in the Workers runtime without any import; do not polyfill it.

---

## Verification

```bash
# 1. Send a test request and capture the trace ID from the response header
TRACE_ID=$(curl -si https://your-worker.example.com/api/data \
  | grep -i x-trace-id | awk '{print $2}' | tr -d '\r')

echo "Trace ID: $TRACE_ID"

# 2. Wait 60 seconds for Analytics Engine ingestion, then query
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{ \"query\": \"SELECT blob4, blob5, double1, double2 FROM request_traces WHERE blob1 = '$TRACE_ID' ORDER BY double3 ASC\" }"

# 3. Confirm you see spans from gateway-worker, auth-worker, and data-worker
```

---

## Related

- `workers-error-rate-alerting-analytics-engine.md`
- `workers-cpu-time-monitoring-tail-workers.md`

---

## Sources

- Cloudflare Analytics Engine documentation — https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API reference — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
