# Distributed Tracing with OpenTelemetry in Cloudflare Workers — W3C traceparent, OTLP Export, Grafana Tempo

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

A request enters your Cloudflare Worker, fans out to a D1 query, a Durable Object, and an upstream API, then returns a response. When p99 latency spikes you can see the total time in Analytics Engine but you cannot tell whether the slow segment is D1, the Durable Object, or the upstream. You need end-to-end distributed tracing that stitches the Worker span, D1 query spans, and Durable Object spans into a single trace visible in Grafana Tempo — without running a sidecar process or modifying Cloudflare's own infrastructure.

---

## Context

Cloudflare Workers do not ship an embedded OpenTelemetry SDK (the standard `@opentelemetry/sdk-node` uses Node.js APIs unavailable in the V8 isolate). The edge-compatible path is:

1. **Create spans manually** using a lightweight trace-context builder (no SDK needed for simple cases) or the `@microlabs/otel-cf-workers` community package, which wraps the OTEL API in Workers-compatible primitives.
2. **Propagate W3C `traceparent`** across Workers, D1 bindings (via SQL comments), Durable Objects (via stub calls), and outbound fetch calls.
3. **Export OTLP spans** to a collector via a Workers Tail Worker — Tail Workers receive a copy of every request/response and all `console.log` entries, making them a natural out-of-band exporter that adds zero latency to the hot path.
4. **Receive and stitch spans** in Grafana Tempo (or any OTLP-compatible backend) using the shared `trace_id` to correlate spans from different services.

---

## Section 1 — Trace Context: Generating and Parsing W3C traceparent

The W3C Trace Context specification defines `traceparent` as:

```
version-traceId-parentSpanId-flags
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

- `version`: always `00`
- `traceId`: 32 hex chars (128-bit)
- `parentSpanId`: 16 hex chars (64-bit)
- `flags`: `01` = sampled, `00` = not sampled

```typescript
// worker/src/lib/trace-context.ts

export interface TraceContext {
  traceId: string;       // 32 hex chars
  spanId: string;        // 16 hex chars
  sampled: boolean;
}

function randomHex(bytes: number): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function generateTraceContext(): TraceContext {
  return {
    traceId: randomHex(16),  // 16 bytes → 32 hex chars
    spanId: randomHex(8),    // 8 bytes  → 16 hex chars
    sampled: true,
  };
}

export function parseTraceparent(header: string | null): TraceContext | null {
  if (!header) return null;
  const parts = header.split("-");
  if (parts.length !== 4 || parts[0] !== "00") return null;
  const [, traceId, parentSpanId, flags] = parts;
  if (!/^[0-9a-f]{32}$/.test(traceId)) return null;
  if (!/^[0-9a-f]{16}$/.test(parentSpanId)) return null;
  return {
    traceId,
    spanId: parentSpanId,
    sampled: (parseInt(flags, 16) & 1) === 1,
  };
}

export function formatTraceparent(ctx: TraceContext, spanId: string): string {
  const flags = ctx.sampled ? "01" : "00";
  return `00-${ctx.traceId}-${spanId}-${flags}`;
}
```

---

## Section 2 — Span Model and the Span Exporter Interface

A minimal span representation compatible with OTLP:

```typescript
// worker/src/lib/tracer.ts

export interface Span {
  traceId: string;
  spanId: string;
  parentSpanId: string | null;
  name: string;
  kind: "server" | "client" | "internal" | "producer" | "consumer";
  startTimeUnixNano: bigint;
  endTimeUnixNano: bigint;
  attributes: Record<string, string | number | boolean>;
  status: { code: 0 | 1 | 2; message?: string }; // 0=unset 1=ok 2=error
  events: Array<{ name: string; timeUnixNano: bigint; attributes?: Record<string, string> }>;
}

export class SpanBuilder {
  private span: Span;

  constructor(
    name: string,
    traceId: string,
    parentSpanId: string | null,
    kind: Span["kind"] = "internal"
  ) {
    const spanId = randomHex(8);
    this.span = {
      traceId,
      spanId,
      parentSpanId,
      name,
      kind,
      startTimeUnixNano: BigInt(Date.now()) * 1_000_000n,
      endTimeUnixNano: 0n,
      attributes: {},
      status: { code: 0 },
      events: [],
    };
  }

  setAttribute(key: string, value: string | number | boolean): this {
    this.span.attributes[key] = value;
    return this;
  }

  addEvent(name: string, attributes?: Record<string, string>): this {
    this.span.events.push({
      name,
      timeUnixNano: BigInt(Date.now()) * 1_000_000n,
      attributes,
    });
    return this;
  }

  setError(message: string): this {
    this.span.status = { code: 2, message };
    this.span.attributes["error"] = true;
    this.span.attributes["error.message"] = message;
    return this;
  }

  end(): Span {
    this.span.endTimeUnixNano = BigInt(Date.now()) * 1_000_000n;
    return { ...this.span };
  }

  get spanId(): string {
    return this.span.spanId;
  }
}

// Import randomHex from trace-context.ts
import { randomHex } from "./trace-context";
```

---

## Section 3 — Instrumenting a Worker Handler

```typescript
// worker/src/index.ts
import { parseTraceparent, generateTraceContext, formatTraceparent } from "./lib/trace-context";
import { SpanBuilder } from "./lib/tracer";
import type { Span } from "./lib/tracer";

export interface Env {
  DB: D1Database;
  COUNTER: DurableObjectNamespace;
  OTEL_EXPORTER_OTLP_ENDPOINT: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // 1. Extract or create trace context
    const incomingCtx = parseTraceparent(request.headers.get("traceparent"));
    const traceCtx = incomingCtx ?? generateTraceContext();

    // 2. Start root span for this Worker invocation
    const rootSpan = new SpanBuilder("worker.fetch", traceCtx.traceId, traceCtx.spanId, "server");
    rootSpan.setAttribute("http.method", request.method);
    rootSpan.setAttribute("http.url", request.url);
    rootSpan.setAttribute("http.scheme", new URL(request.url).protocol.replace(":", ""));
    rootSpan.setAttribute("cf.colo", (request as any).cf?.colo ?? "unknown");

    const spans: Span[] = [];

    try {
      // 3. Instrument D1 query
      const dbSpan = new SpanBuilder("d1.query", traceCtx.traceId, rootSpan.spanId, "client");
      dbSpan.setAttribute("db.system", "sqlite");
      dbSpan.setAttribute("db.statement", "SELECT * FROM users WHERE id = ?");

      const result = await env.DB.prepare("SELECT * FROM users WHERE id = ?")
        .bind(1)
        .first();

      dbSpan.setAttribute("db.rows_returned", result ? 1 : 0);
      spans.push(dbSpan.end());

      // 4. Instrument Durable Object call
      const doSpan = new SpanBuilder("durable-object.fetch", traceCtx.traceId, rootSpan.spanId, "client");
      doSpan.setAttribute("do.name", "counter");

      const doId = env.COUNTER.idFromName("global");
      const doStub = env.COUNTER.get(doId);
      const doReq = new Request("https://do-internal/increment", {
        method: "POST",
        headers: {
          // Propagate trace context into the DO
          traceparent: formatTraceparent(traceCtx, doSpan.spanId),
        },
      });
      const doRes = await doStub.fetch(doReq);
      doSpan.setAttribute("do.status", doRes.status);
      spans.push(doSpan.end());

      // 5. End root span
      rootSpan.setAttribute("http.status_code", 200);
      spans.push(rootSpan.end());

      // 6. Export spans out-of-band (non-blocking)
      ctx.waitUntil(exportSpans(spans, env.OTEL_EXPORTER_OTLP_ENDPOINT));

      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          // Propagate trace context to the downstream client
          traceparent: formatTraceparent(traceCtx, rootSpan.spanId),
        },
      });
    } catch (err) {
      rootSpan.setError(err instanceof Error ? err.message : String(err));
      spans.push(rootSpan.end());
      ctx.waitUntil(exportSpans(spans, env.OTEL_EXPORTER_OTLP_ENDPOINT));
      return new Response("Internal Server Error", { status: 500 });
    }
  },
};
```

---

## Section 4 — Exporting OTLP Spans via Workers Tail

The Tail Worker pattern decouples span export from the hot path. The primary Worker logs spans as structured JSON to `console.log`, and a Tail Worker listens, deserializes, and forwards them to the OTLP collector.

**Primary Worker — serialize spans to console:**

```typescript
// worker/src/lib/exporter.ts
import type { Span } from "./tracer";

export async function exportSpans(
  spans: Span[],
  endpoint: string
): Promise<void> {
  if (spans.length === 0) return;

  // Structured log — Tail Worker picks this up
  console.log(
    JSON.stringify({
      __otel_spans: true,
      spans: spans.map(serializeSpan),
    })
  );
}

function serializeSpan(span: Span) {
  return {
    traceId: span.traceId,
    spanId: span.spanId,
    parentSpanId: span.parentSpanId ?? undefined,
    name: span.name,
    kind: kindToInt(span.kind),
    startTimeUnixNano: span.startTimeUnixNano.toString(),
    endTimeUnixNano: span.endTimeUnixNano.toString(),
    attributes: Object.entries(span.attributes).map(([k, v]) => ({
      key: k,
      value: typeof v === "string"
        ? { stringValue: v }
        : typeof v === "number"
        ? { doubleValue: v }
        : { boolValue: v },
    })),
    status: span.status,
    events: span.events.map((e) => ({
      name: e.name,
      timeUnixNano: e.timeUnixNano.toString(),
      attributes: Object.entries(e.attributes ?? {}).map(([k, v]) => ({
        key: k,
        value: { stringValue: v },
      })),
    })),
  };
}

function kindToInt(kind: Span["kind"]): number {
  return { server: 2, client: 3, producer: 4, consumer: 5, internal: 1 }[kind];
}
```

**Tail Worker — forward to OTLP collector:**

```typescript
// tail-worker/src/index.ts
export interface TailEnv {
  OTEL_ENDPOINT: string;   // e.g. https://tempo.example.com/otlp/v1/traces
  OTEL_HEADERS: string;    // JSON string: {"Authorization": "Bearer ..."}
}

export default {
  async tail(events: TraceItem[], env: TailEnv): Promise<void> {
    const allSpans: unknown[] = [];

    for (const event of events) {
      for (const log of event.logs ?? []) {
        if (typeof log.message[0] !== "string") continue;
        try {
          const parsed = JSON.parse(log.message[0]);
          if (parsed.__otel_spans && Array.isArray(parsed.spans)) {
            allSpans.push(...parsed.spans);
          }
        } catch {
          // Not a structured span log — ignore
        }
      }
    }

    if (allSpans.length === 0) return;

    const otlpPayload = {
      resourceSpans: [
        {
          resource: {
            attributes: [
              { key: "service.name", value: { stringValue: "my-worker" } },
              { key: "deployment.environment", value: { stringValue: "production" } },
              { key: "cloud.provider", value: { stringValue: "cloudflare" } },
            ],
          },
          scopeSpans: [
            {
              scope: { name: "orchords-worker-tracer", version: "1.0.0" },
              spans: allSpans,
            },
          ],
        },
      ],
    };

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(JSON.parse(env.OTEL_HEADERS) as Record<string, string>),
    };

    await fetch(`${env.OTEL_ENDPOINT}/v1/traces`, {
      method: "POST",
      headers,
      body: JSON.stringify(otlpPayload),
    });
  },
} satisfies ExportedHandler<TailEnv>;
```

Wire the Tail Worker in `wrangler.toml`:

```toml
# Primary worker
name = "my-worker"
main = "src/index.ts"

[[tail_consumers]]
  service = "my-worker-tail"

# Tail worker (separate wrangler.toml or same monorepo)
name = "my-worker-tail"
main = "tail-worker/src/index.ts"

[vars]
  OTEL_ENDPOINT = "https://tempo.example.com/otlp"
  OTEL_HEADERS  = '{"Authorization":"Bearer YOUR_TEMPO_TOKEN"}'
```

---

## Section 5 — Instrumenting Durable Objects to Emit Child Spans

Inside the Durable Object, parse the incoming `traceparent` and emit spans that share the same `traceId`:

```typescript
// durable-objects/counter.ts
import { parseTraceparent, formatTraceparent } from "../worker/src/lib/trace-context";
import { SpanBuilder } from "../worker/src/lib/tracer";

export class Counter implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const incoming = parseTraceparent(request.headers.get("traceparent"));
    if (!incoming) {
      return new Response("Missing traceparent", { status: 400 });
    }

    const span = new SpanBuilder(
      "do.counter.increment",
      incoming.traceId,
      incoming.spanId,   // parent = the span that called this DO
      "server"
    );
    span.setAttribute("do.class", "Counter");
    span.setAttribute("do.method", "increment");

    try {
      const current = (await this.state.storage.get<number>("count")) ?? 0;
      const next = current + 1;
      await this.state.storage.put("count", next);

      span.setAttribute("do.count", next);
      const finished = span.end();

      // Tail Worker will pick up this log from the DO's execution context
      console.log(JSON.stringify({ __otel_spans: true, spans: [finished] }));

      return new Response(JSON.stringify({ count: next }), {
        headers: {
          "Content-Type": "application/json",
          traceparent: formatTraceparent(incoming, span.spanId),
        },
      });
    } catch (err) {
      span.setError(err instanceof Error ? err.message : String(err));
      console.log(JSON.stringify({ __otel_spans: true, spans: [span.end()] }));
      throw err;
    }
  }
}
```

---

## Section 6 — Stitching Traces in Grafana Tempo

Tempo accepts OTLP over HTTP/JSON or gRPC. Configure the datasource in Grafana:

```yaml
# grafana/provisioning/datasources/tempo.yaml
apiVersion: 1
datasources:
  - name: Tempo
    type: tempo
    url: http://tempo:3200
    jsonData:
      tracesToLogsV2:
        datasourceUid: loki
        filterByTraceID: true
        filterBySpanID: false
      serviceMap:
        datasourceUid: prometheus
      search:
        hide: false
      lokiSearch:
        datasourceUid: loki
```

Query traces by `traceId` directly in the Tempo Explore panel:

```
# TraceQL — find all traces for your Worker service
{ resource.service.name="my-worker" && duration > 500ms }

# Find the specific span types
{ span.db.system="sqlite" } | select(duration, span.db.statement)

# Find error spans
{ status=error && resource.service.name="my-worker" }
```

Correlate with Loki logs using the `traceId` as a log label. In the Tail Worker, also log a structured JSON line with `traceId`:

```typescript
// In your primary Worker handler, emit a correlation log
console.log(
  JSON.stringify({
    level: "info",
    traceId: traceCtx.traceId,
    spanId: rootSpan.spanId,
    message: `${request.method} ${new URL(request.url).pathname}`,
    status: 200,
    durationMs: Number((rootSpan.endTimeUnixNano - rootSpan.startTimeUnixNano) / 1_000_000n),
  })
);
```

Configure Loki to index the `traceId` field and Grafana's derived fields to link from a log line's `traceId` value to the corresponding Tempo trace.

---

## Anti-Patterns

- **Exporting spans synchronously on the hot path.** A `await fetch(otlpEndpoint, ...)` inside the request handler adds 50–200 ms to every response. Always use `ctx.waitUntil()` or the Tail Worker pattern for export.
- **Using `@opentelemetry/sdk-node` in a Worker.** It imports Node.js `os`, `fs`, and `crypto` modules that do not exist in V8. Use `@microlabs/otel-cf-workers` or the manual approach shown above.
- **Losing the trace ID across D1 query boundaries.** D1 does not automatically propagate `traceparent`. Add it as a SQL comment if your collector can parse it, or manage the parent-child span relationship explicitly in code.
- **Generating non-random span IDs.** Using incrementing integers or timestamps for span IDs causes collisions across concurrent requests. Always use `crypto.getRandomValues()`.
- **Storing span data in KV or D1 and exporting later.** This adds storage cost, read latency on export, and retention concerns. The Tail Worker pattern is purpose-built for this use case.
- **Sampling 100% of requests in production.** High-throughput Workers generate millions of spans per hour. Implement head-based sampling at the root span level (check `traceparent` flags, or use a deterministic hash of `traceId` modulo a sampling rate).

---

## Gotchas

1. **Tail Worker latency.** Tail Workers receive events after the primary Worker has responded. Spans appear in Tempo 1–10 seconds after the request completes. Do not use tail-exported traces for real-time alerting — use Analytics Engine metrics for that.
2. **`console.log` size limit in Tail Workers.** Workers Tail captures up to 128 KB of log output per request. A request that creates hundreds of spans (e.g., bulk D1 inserts) may be truncated. Batch spans into a single `console.log` call rather than one call per span.
3. **BigInt serialization.** `JSON.stringify` throws on BigInt values. Convert nanosecond timestamps to strings with `.toString()` before serializing.
4. **Durable Object tail events.** Tail Workers receive events from both the primary Worker and Durable Objects — they are separate tail event entries. Ensure your Tail Worker accumulates spans from all entries in the `events` array, not just the first.
5. **W3C `tracestate` header.** If downstream services send a `tracestate` header alongside `traceparent`, forward it unchanged. Do not modify or drop it — it carries vendor-specific context (e.g., Datadog's `dd=s:1;t.tid:...`).
6. **Tempo's `traceId` format.** Tempo expects `traceId` as a 32-character hex string. Some OTLP collectors accept 16-character (64-bit) trace IDs but Tempo requires 128-bit. Always use 32 hex chars.

---

## Verification

```bash
# 1. Send a test request with a known traceId
curl -X GET https://my-worker.example.com/api/users \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  -v

# 2. Check Tempo for the trace (allow 5–10s for Tail Worker export)
curl "https://tempo.example.com/api/traces/4bf92f3577b34da6a3ce929d0e0e4736" \
  -H "Authorization: Bearer YOUR_TEMPO_TOKEN" | jq '.batches[].scopeSpans[].spans[].name'

# Expected output:
# "worker.fetch"
# "d1.query"
# "durable-object.fetch"
# "do.counter.increment"

# 3. Verify Tail Worker is receiving events
wrangler tail my-worker-tail --format pretty

# 4. Validate OTLP payload format
# Use otelcol's debug exporter locally:
docker run --rm -p 4318:4318 \
  otel/opentelemetry-collector-contrib:0.102.0 \
  --config /etc/otel/config.yaml
# Point OTEL_ENDPOINT to http://localhost:4318/otlp and watch the collector logs
```

---

## Related Articles

- `documentation/docs/policies/monitoring/distributed-tracing-workers-d1-durable-objects-otel.md`
- `documentation/docs/policies/monitoring/w3c-trace-context-propagation.md`
- `documentation/docs/policies/monitoring/opentelemetry-overview.md`
- `documentation/docs/policies/monitoring/opentelemetry-baggage-propagation.md`
- `documentation/docs/policies/monitoring/workers-tail-real-time-log-streaming.md`
- `documentation/docs/policies/monitoring/cloudflare-queues-async-tracing.md`
- `documentation/docs/policies/monitoring/grafana-datasource-config.md`

---

## Sources

- W3C Trace Context Level 1 — https://www.w3.org/TR/trace-context/
- OpenTelemetry OTLP/JSON spec — https://opentelemetry.io/docs/specs/otlp/
- `@microlabs/otel-cf-workers` — https://github.com/evanderkoogh/otel-cf-workers
- Cloudflare Workers Tail — https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- Grafana Tempo — https://grafana.com/docs/tempo/latest/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- TraceQL — https://grafana.com/docs/tempo/latest/traceql/
