# Exporting OpenTelemetry Traces from Workers to a Jaeger-Compatible Collector

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want distributed tracing across multiple Cloudflare Workers and downstream services without running a Node.js process or the full OpenTelemetry SDK. You need spans serialized as OTLP JSON, fanned out through a Queue consumer to avoid blocking the hot path, and sampled at 10% to stay within collector ingest budgets.

---

## Context
The OpenTelemetry JavaScript SDK (`@opentelemetry/sdk-node`) depends on Node.js APIs unavailable in the Workers runtime. However, the `@opentelemetry/api` package is runtime-agnostic and can be used to create and manage spans. Spans are serialized manually as OTLP/JSON (Protobuf encoding is not used because it requires a build step that bloats the Worker bundle). A Queue consumer Worker receives batches of serialized spans and POSTs them to any OTLP-compatible collector (Jaeger ≥1.35 with OTLP HTTP receiver, Grafana Tempo, Honeycomb). Parent context is propagated between Workers via the standard `traceparent` W3C header, enabling end-to-end traces across service boundaries.

---

## Setup / Config

```toml
# wrangler.toml  (producer Worker)
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[queues.producers]]
binding = "TRACE_QUEUE"
queue = "otel-spans"

[vars]
OTEL_SAMPLE_RATE = "0.1"   # 10% sampling
OTEL_SERVICE_NAME = "api-worker"
```

```toml
# wrangler.toml  (consumer Worker — separate file or same repo)
name = "otel-exporter"
main = "src/exporter.ts"
compatibility_date = "2024-09-23"

[[queues.consumers]]
queue = "otel-spans"
max_batch_size = 100
max_batch_timeout = 5

[vars]
COLLECTOR_ENDPOINT = "https://jaeger.internal.example.com/v1/traces"
```

```bash
# Install only the API package (no SDK, no Node.js deps)
npm install @opentelemetry/api
```

---

## Implementation — OTLP Span Model

```typescript
// src/otel.ts

/** Minimal OTLP/JSON span representation (subset of the full spec). */
export interface OtlpSpan {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  kind: number; // SpanKind: 1=INTERNAL, 2=SERVER, 3=CLIENT
  startTimeUnixNano: string;
  endTimeUnixNano: string;
  attributes: Array<{ key: string; value: { stringValue?: string; intValue?: string; doubleValue?: number; boolValue?: boolean } }>;
  status: { code: number }; // 0=UNSET, 1=OK, 2=ERROR
}

export interface OtlpExportRequest {
  resourceSpans: Array<{
    resource: { attributes: Array<{ key: string; value: { stringValue: string } }> };
    scopeSpans: Array<{
      scope: { name: string; version: string };
      spans: OtlpSpan[];
    }>;
  }>;
}

/** Generate a random 16-byte hex trace ID. */
export function generateTraceId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Generate a random 8-byte hex span ID. */
export function generateSpanId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(8)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Parse W3C traceparent header: `00-traceId-spanId-flags` */
export function parseTraceparent(
  header: string | null
): { traceId: string; spanId: string } | null {
  if (!header) return null;
  const parts = header.split("-");
  if (parts.length !== 4 || parts[0] !== "00") return null;
  return { traceId: parts[1], spanId: parts[2] };
}

/** Nanoseconds since Unix epoch as a decimal string (BigInt). */
function nowNano(): string {
  return (BigInt(Date.now()) * 1_000_000n).toString();
}

export interface SpanData {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  kind?: number;
  startNano: string;
  endNano: string;
  attributes?: Record<string, string | number | boolean>;
  errorMessage?: string;
}

export function buildOtlpPayload(
  spans: SpanData[],
  serviceName: string
): OtlpExportRequest {
  return {
    resourceSpans: [
      {
        resource: {
          attributes: [
            { key: "service.name", value: { stringValue: serviceName } },
          ],
        },
        scopeSpans: [
          {
            scope: { name: "workers-otel", version: "0.1.0" },
            spans: spans.map((s) => ({
              traceId: s.traceId,
              spanId: s.spanId,
              ...(s.parentSpanId ? { parentSpanId: s.parentSpanId } : {}),
              name: s.name,
              kind: s.kind ?? 2,
              startTimeUnixNano: s.startNano,
              endTimeUnixNano: s.endNano,
              attributes: Object.entries(s.attributes ?? {}).map(([k, v]) => ({
                key: k,
                value:
                  typeof v === "boolean"
                    ? { boolValue: v }
                    : typeof v === "number"
                    ? { doubleValue: v }
                    : { stringValue: String(v) },
              })),
              status: { code: s.errorMessage ? 2 : 1 },
            })),
          },
        ],
      },
    ],
  };
}
```

```typescript
// src/index.ts  (producer Worker)
import {
  generateTraceId,
  generateSpanId,
  parseTraceparent,
  SpanData,
} from "./otel";

export interface Env {
  TRACE_QUEUE: Queue<SpanData>;
  OTEL_SAMPLE_RATE: string;
  OTEL_SERVICE_NAME: string;
}

/** Returns true if this request should be traced (10% by default). */
function shouldSample(rate: string): boolean {
  return Math.random() < parseFloat(rate);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!shouldSample(env.OTEL_SAMPLE_RATE)) {
      // Fast path: no tracing overhead
      return new Response(JSON.stringify({ ok: true }), {
        headers: { "content-type": "application/json" },
      });
    }

    // Extract parent context from incoming traceparent
    const parent = parseTraceparent(request.headers.get("traceparent"));
    const traceId = parent?.traceId ?? generateTraceId();
    const spanId = generateSpanId();
    const startNano = (BigInt(Date.now()) * 1_000_000n).toString();

    let responseStatus = 200;
    try {
      const response = new Response(JSON.stringify({ ok: true }), {
        headers: {
          "content-type": "application/json",
          // Propagate trace context to downstream services
          traceparent: `00-${traceId}-${spanId}-01`,
        },
      });
      responseStatus = response.status;
      return response;
    } finally {
      const endNano = (BigInt(Date.now()) * 1_000_000n).toString();

      const span: SpanData = {
        traceId,
        spanId,
        ...(parent?.spanId ? { parentSpanId: parent.spanId } : {}),
        name: `${request.method} ${new URL(request.url).pathname}`,
        kind: 2, // SERVER
        startNano,
        endNano,
        attributes: {
          "http.method": request.method,
          "http.url": request.url,
          "http.status_code": responseStatus,
          "cf.colo": (request as unknown as { cf?: { colo?: string } }).cf?.colo ?? "unknown",
        },
      };

      // Non-blocking enqueue — does not add latency to the response
      await env.TRACE_QUEUE.send(span);
    }
  },
};
```

---

## Queue Consumer — Batch Export to Collector

```typescript
// src/exporter.ts
import { buildOtlpPayload, SpanData } from "./otel";

export interface Env {
  COLLECTOR_ENDPOINT: string;
  OTEL_SERVICE_NAME: string;
}

export default {
  async queue(
    batch: MessageBatch<SpanData>,
    env: Env
  ): Promise<void> {
    const spans = batch.messages.map((m) => m.body);

    if (spans.length === 0) return;

    const payload = buildOtlpPayload(spans, env.OTEL_SERVICE_NAME ?? "worker");

    const response = await fetch(env.COLLECTOR_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      // Returning without ack causes the batch to be retried
      throw new Error(
        `Collector returned ${response.status}: ${await response.text()}`
      );
    }

    batch.ackAll();
  },
};
```

---

## Anti-patterns
- **Blocking the response on `await queue.send()`** — always put the enqueue inside a `finally` block after the response is constructed; the response is returned before the enqueue resolves.
- **Sending unsampled traces** — apply the sampling decision before creating any span objects; creating spans unconditionally and discarding them wastes CPU.
- **Using `@opentelemetry/sdk-node`** — it imports `os`, `process`, and `fs` which are not available in Workers; only `@opentelemetry/api` is safe to import.
- **Propagating `traceparent` as a response header to end users** — only set it on internal service-to-service calls to avoid leaking trace IDs to browsers.

---

## Gotchas
- Workers Queues deliver messages at least once; your collector must be idempotent, or deduplicate by `spanId`.
- `BigInt` arithmetic for nanoseconds is required; `Date.now()` returns milliseconds and `number` cannot represent nanosecond timestamps without precision loss.
- Queue consumers run in a separate isolate from the producer; the `SpanData` object must be JSON-serializable (no `Date`, `BigInt`, `undefined` values).
- The Jaeger OTLP HTTP receiver listens on port 4318 by default; ensure the collector is reachable from Workers egress IPs.
- 10% sampling means 9 out of 10 requests produce no spans; adjust `OTEL_SAMPLE_RATE` per environment (100% in staging, 10% in production).

---

## Verification

```bash
# Deploy both Workers
wrangler deploy --config wrangler.toml          # producer
wrangler deploy --config wrangler.exporter.toml # consumer

# Send 20 requests (expect ~2 traces at 10% sampling)
for i in $(seq 1 20); do
  curl -s https://api-worker.example.workers.dev/ > /dev/null
done

# Check Jaeger UI
open http://jaeger.internal.example.com:16686
# Search for service: api-worker
# You should see approximately 2 traces

# Verify Queue message delivery
wrangler queues list
# inspect otel-spans consumer lag — should be near 0 after ~10s
```

---

## Related
- `workers-d1-query-trace-structured-log.md`
- `workers-analytics-engine-funnel-tracking.md`

---

## Sources
- OpenTelemetry OTLP/JSON specification — https://opentelemetry.io/docs/specs/otlp/
- Cloudflare Workers Queues — https://developers.cloudflare.com/queues/
- W3C Trace Context (traceparent) — https://www.w3.org/TR/trace-context/
- Jaeger OTLP HTTP receiver — https://www.jaegertracing.io/docs/latest/apis/#otlp-via-http
