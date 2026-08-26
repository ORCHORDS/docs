# Distributed Tracing: Workers → D1 → Durable Objects with OpenTelemetry

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project's playback session flow touches three Cloudflare primitives in
sequence: an edge Worker handles the HTTP request, queries D1 for track
metadata, and then forwards websocket events to a Durable Object (DO) that
manages the per-session state. A latency regression at the DO layer is
invisible in standard Workers metrics because Cloudflare reports CPU time
per Worker invocation, not across a request's full lifetime including DO
stub calls.

Without end-to-end trace context:
- A 900 ms p99 latency appears attributable to the edge Worker.
- The true culprit (a DO alarm handler holding a write lock for 800 ms)
  is never surfaced.
- Mobile sessions (which maintain long-lived websocket connections) are
  disproportionately affected but the aggregate hides it.

---

## Context

Durable Objects run as isolated single-threaded Workers with their own
CPU budget. They are reached via a stub (`env.SESSION_DO.get(id)`) that
makes an internal sub-request — this is a real network hop that adds
latency and is NOT included in the calling Worker's CPU time metric.

OpenTelemetry (OTel) context propagation across these hops requires:
1. The calling Worker creates a root span and injects `traceparent` /
   `tracestate` headers before calling the DO stub.
2. The DO extracts the trace context from the incoming request and creates
   a child span.
3. Both Workers export spans via `fetch()` to an OTel Collector (or
   directly to a backend like Honeycomb or Grafana Tempo) inside
   `ctx.waitUntil`.
4. D1 queries are wrapped with a child span recording the SQL statement
   and elapsed time.

Mobile and desktop sessions are tracked via a `device_type` span
attribute so Grafana Tempo's TraceQL can filter:
`{ .device_type = "mobile" } | duration > 500ms`.

---

## Section 1: Minimal OTel Span Implementation for Workers Runtime

The Workers runtime does not support the full OTel SDK (Node.js
dependencies). Use a lightweight hand-rolled implementation that produces
valid OTLP/JSON payloads.

```typescript
// src/lib/otel.ts
export type SpanKind = "SERVER" | "CLIENT" | "INTERNAL" | "PRODUCER" | "CONSUMER";

export interface Span {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  kind: SpanKind;
  startTimeUnixNano: bigint;
  endTimeUnixNano?: bigint;
  attributes: Record<string, string | number | boolean>;
  status: "UNSET" | "OK" | "ERROR";
  events: Array<{ name: string; timeUnixNano: bigint; attributes?: Record<string, string> }>;
}

function randomHex(bytes: number): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return Array.from(arr).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function createRootSpan(name: string, kind: SpanKind = "SERVER"): Span {
  return {
    traceId: randomHex(16),
    spanId:  randomHex(8),
    name,
    kind,
    startTimeUnixNano: BigInt(Date.now()) * 1_000_000n,
    attributes: {},
    status: "UNSET",
    events: [],
  };
}

export function createChildSpan(parent: Span, name: string, kind: SpanKind = "CLIENT"): Span {
  return {
    traceId:       parent.traceId,
    spanId:        randomHex(8),
    parentSpanId:  parent.spanId,
    name,
    kind,
    startTimeUnixNano: BigInt(Date.now()) * 1_000_000n,
    attributes: {},
    status: "UNSET",
    events: [],
  };
}

export function endSpan(span: Span, error?: Error): Span {
  span.endTimeUnixNano = BigInt(Date.now()) * 1_000_000n;
  if (error) {
    span.status = "ERROR";
    span.attributes["exception.message"] = error.message;
    span.attributes["exception.type"]    = error.name;
  } else {
    span.status = "OK";
  }
  return span;
}

export function traceparentHeader(span: Span): string {
  return `00-${span.traceId}-${span.spanId}-01`;
}

export function extractTraceContext(request: Request): { traceId: string; parentSpanId: string } | null {
  const header = request.headers.get("traceparent");
  if (!header) return null;
  const parts = header.split("-");
  if (parts.length < 4) return null;
  return { traceId: parts[1], parentSpanId: parts[2] };
}
```

---

## Section 2: OTLP Exporter

```typescript
// src/lib/otel-exporter.ts
import type { Span } from "./otel";

function spanKindToInt(kind: string): number {
  const map: Record<string, number> = {
    SERVER: 2, CLIENT: 3, INTERNAL: 1, PRODUCER: 4, CONSUMER: 5,
  };
  return map[kind] ?? 0;
}

export async function exportSpans(
  spans: Span[],
  endpoint: string,
  apiKey: string,
): Promise<void> {
  const body = {
    resourceSpans: [{
      resource: {
        attributes: [
          { key: "service.name",    value: { stringValue: "example project-api" } },
          { key: "service.version", value: { stringValue: "1.0.0" } },
        ],
      },
      scopeSpans: [{
        scope: { name: "example project-tracer", version: "0.1.0" },
        spans: spans.map((s) => ({
          traceId:           s.traceId,
          spanId:            s.spanId,
          parentSpanId:      s.parentSpanId,
          name:              s.name,
          kind:              spanKindToInt(s.kind),
          startTimeUnixNano: s.startTimeUnixNano.toString(),
          endTimeUnixNano:   (s.endTimeUnixNano ?? BigInt(Date.now()) * 1_000_000n).toString(),
          attributes: Object.entries(s.attributes).map(([k, v]) => ({
            key:   k,
            value: typeof v === "number"
              ? { doubleValue: v }
              : typeof v === "boolean"
              ? { boolValue: v }
              : { stringValue: String(v) },
          })),
          status: { code: s.status === "OK" ? 1 : s.status === "ERROR" ? 2 : 0 },
          events: s.events.map((e) => ({
            name:              e.name,
            timeUnixNano:      e.timeUnixNano.toString(),
            attributes:        Object.entries(e.attributes ?? {}).map(([k, v]) => ({
              key: k, value: { stringValue: v },
            })),
          })),
        })),
      }],
    }],
  };

  await fetch(endpoint, {
    method:  "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key":    apiKey,
    },
    body: JSON.stringify(body),
  });
}
```

---

## Section 3: Edge Worker — Root Span + D1 + DO Stub

```typescript
// src/index.ts
import {
  createRootSpan, createChildSpan, endSpan, traceparentHeader,
} from "./lib/otel";
import { exportSpans } from "./lib/otel-exporter";
import { resolveDeviceType } from "./lib/device";

interface Env {
  APP_DB:      D1Database;
  SESSION_DO:  DurableObjectNamespace;
  OTEL_ENDPOINT: string;   // e.g. https://api.honeycomb.io/v1/traces
  OTEL_API_KEY:  string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const deviceType = resolveDeviceType(request);
    const rootSpan   = createRootSpan("http.request", "SERVER");
    rootSpan.attributes["http.method"]  = request.method;
    rootSpan.attributes["http.url"]     = request.url;
    rootSpan.attributes["device_type"]  = deviceType;
    rootSpan.attributes["http.route"]   = new URL(request.url).pathname;
    rootSpan.attributes["net.peer.ip"]  = request.headers.get("CF-Connecting-IP") ?? "";

    const spans: Parameters<typeof exportSpans>[0] = [];
    let response: Response;

    try {
      // --- D1 query with child span ---
      const d1Span = createChildSpan(rootSpan, "d1.query", "CLIENT");
      d1Span.attributes["db.system"]    = "sqlite";
      d1Span.attributes["db.name"]      = "example project-production";

      const sql = "SELECT id, title, artist FROM tracks WHERE id = ? LIMIT 1";
      const trackId = new URL(request.url).searchParams.get("track_id") ?? "0";
      d1Span.attributes["db.statement"] = sql;

      let track: Record<string, unknown> | null = null;
      try {
        track = await env.APP_DB.prepare(sql).bind(trackId).first();
        endSpan(d1Span);
      } catch (err) {
        endSpan(d1Span, err as Error);
        throw err;
      } finally {
        spans.push(d1Span);
      }

      // --- Durable Object call with child span ---
      const doSpan = createChildSpan(rootSpan, "durable_object.session", "CLIENT");
      doSpan.attributes["do.class"]     = "PlaybackSession";
      doSpan.attributes["do.id"]        = trackId;
      doSpan.attributes["device_type"]  = deviceType;

      const doId   = env.SESSION_DO.idFromName(`session-${trackId}`);
      const doStub = env.SESSION_DO.get(doId);

      const doRequest = new Request("https://internal.do/state", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "traceparent":  traceparentHeader(doSpan),    // propagate context
          "x-device-type": deviceType,
        },
        body: JSON.stringify({ trackId, track }),
      });

      try {
        response = await doStub.fetch(doRequest);
        doSpan.attributes["http.status_code"] = response.status;
        endSpan(doSpan);
      } catch (err) {
        endSpan(doSpan, err as Error);
        throw err;
      } finally {
        spans.push(doSpan);
      }

      rootSpan.attributes["http.status_code"] = response.status;
      endSpan(rootSpan);

    } catch (err) {
      endSpan(rootSpan, err as Error);
      response = new Response("Internal Server Error", { status: 500 });
    } finally {
      spans.unshift(rootSpan);
    }

    ctx.waitUntil(
      exportSpans(spans, env.OTEL_ENDPOINT, env.OTEL_API_KEY).catch(() => {}),
    );

    return response!;
  },
};
```

---

## Section 4: Durable Object — Child Span Extraction

```typescript
// src/PlaybackSession.ts
import {
  createChildSpan, endSpan, extractTraceContext,
} from "./lib/otel";
import { exportSpans } from "./lib/otel-exporter";

interface Env {
  OTEL_ENDPOINT: string;
  OTEL_API_KEY:  string;
}

export class PlaybackSession {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const traceCtx   = extractTraceContext(request);
    const deviceType = request.headers.get("x-device-type") ?? "unknown";

    // Re-create a pseudo-parent span from the injected context
    const parentSpan = traceCtx
      ? { traceId: traceCtx.traceId, spanId: traceCtx.parentSpanId }
      : null;

    const doSpan = parentSpan
      ? {
          ...createChildSpan(
            { ...parentSpan, name: "", kind: "CLIENT" as const,
              startTimeUnixNano: BigInt(0), attributes: {}, status: "UNSET" as const, events: [] },
            "do.handle_state", "INTERNAL",
          ),
          traceId:      parentSpan.traceId,
          parentSpanId: parentSpan.spanId,
        }
      : createChildSpan(
          { traceId: "0".repeat(32), spanId: "0".repeat(16), name: "", kind: "SERVER" as const,
            startTimeUnixNano: BigInt(0), attributes: {}, status: "UNSET" as const, events: [] },
          "do.handle_state", "INTERNAL",
        );

    doSpan.attributes["device_type"] = deviceType;
    doSpan.attributes["do.class"]    = "PlaybackSession";

    let result: Response;
    try {
      const body = await request.json<{ trackId: string; track: unknown }>();
      await this.state.storage.put(`track:${body.trackId}`, body.track);

      doSpan.attributes["do.storage.writes"] = 1;
      endSpan(doSpan);
      result = Response.json({ ok: true });
    } catch (err) {
      endSpan(doSpan, err as Error);
      result = new Response("DO Error", { status: 500 });
    }

    // Export DO span independently — DO has its own isolate and waitUntil
    this.state.waitUntil(
      exportSpans([doSpan], this.env.OTEL_ENDPOINT, this.env.OTEL_API_KEY).catch(() => {}),
    );

    return result;
  }
}
```

```toml
# wrangler.toml
name = "example project-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
OTEL_ENDPOINT = "https://api.honeycomb.io/v1/traces"

[secrets]
# wrangler secret put OTEL_API_KEY

[[d1_databases]]
binding = "APP_DB"
database_name = "example project-production"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[durable_objects.bindings]]
name       = "SESSION_DO"
class_name = "PlaybackSession"

[[migrations]]
tag  = "v1"
new_classes = ["PlaybackSession"]
```

---

## Anti-patterns

- **Synchronously exporting spans on the hot path** — `fetch()` to an
  OTel endpoint inside the request handler blocks the response. Always
  wrap in `ctx.waitUntil` (Worker) or `this.state.waitUntil` (DO).
- **Generating a new traceId in the DO instead of propagating** — the
  entire value of distributed tracing collapses if the DO creates an
  independent trace. Always inject `traceparent` in the DO-bound request.
- **Storing traceIds in D1** — do not write trace context to the
  application database. It bloats the schema and is unnecessary when the
  trace backend handles correlation.
- **Tracing every DO alarm invocation** — alarms fire frequently and
  have their own CPU budget. Trace alarms at a 1-in-10 sample rate to
  avoid saturating the OTel backend.
- **Using `performance.now()` for span timestamps** — `performance.now()`
  resets per invocation. Use `Date.now()` converted to nanoseconds for
  absolute timestamps compatible with OTLP.

---

## Gotchas

- Durable Objects share the same `wrangler.toml` as their calling Worker
  but run in a different isolate. The `OTEL_ENDPOINT` and `OTEL_API_KEY`
  bindings must be accessible to the DO class — they are if declared in
  `[vars]` / secrets and the DO is in the same Worker bundle.
- `this.state.waitUntil` in a DO requires `compatibility_date` of
  `2024-04-01` or later. Earlier compatibility dates do not support it —
  the DO fetch handler will return before the span export completes.
- The W3C `traceparent` header format is `00-{traceId}-{parentSpanId}-{flags}`.
  `flags = 01` means sampled; `00` means not sampled. Always send `01`
  unless you implement head-based sampling.
- DO sub-requests appear as "unknown" service in some OTel backends
  because the `service.name` resource attribute is per-export call.
  Set `service.name = "example project-session-do"` in the DO's `exportSpans` call
  to distinguish DO spans from edge Worker spans in Tempo / Honeycomb.
- `bigint` arithmetic for nanosecond timestamps (`BigInt(Date.now()) * 1_000_000n`)
  requires `--target es2020` or later in your TypeScript config. The
  Workers runtime supports bigint natively.

---

## Verification

```bash
# Deploy and send a test request
wrangler deploy
curl "https://example project-api.workers.dev/?track_id=42" \
  -H "x-forwarded-for: 1.2.3.4"

# In Honeycomb / Tempo / Grafana — search for:
# service.name = "example project-api" AND device_type = "mobile"
# You should see a trace with 3 spans:
#   1. http.request (root)
#   2. d1.query (child of 1)
#   3. durable_object.session (child of 1)
# And a separate trace with 1 span exported by the DO:
#   4. do.handle_state (linked to span 3 via traceId)

# Confirm traceparent is propagated by inspecting DO request logs:
wrangler tail --format pretty | grep traceparent
```

TraceQL query for Grafana Tempo to find slow mobile sessions:

```
{ resource.service.name = "example project-api" && span.device_type = "mobile" }
| duration > 500ms
```

---

## Related

- `distributed-tracing-workers-d1-requests.md`
- `opentelemetry-custom-spans.md`
- `opentelemetry-baggage-propagation.md`
- `w3c-trace-context-propagation.md`
- `analytics-engine-mobile-desktop-segmentation.md`

---

## Sources

- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- W3C Trace Context specification — https://www.w3.org/TR/trace-context/
- OpenTelemetry Protocol (OTLP) JSON encoding — https://opentelemetry.io/docs/specs/otlp/
- Grafana Tempo TraceQL — https://grafana.com/docs/tempo/latest/traceql/
- Cloudflare Workers `waitUntil` — https://developers.cloudflare.com/workers/runtime-apis/context/
