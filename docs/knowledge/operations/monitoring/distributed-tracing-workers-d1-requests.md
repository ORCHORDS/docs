# Distributed Tracing — Cloudflare Workers + D1 Requests

Date:   2026-08-22
Author: example.com
Status: active

---

## Symptom

example project API latency spikes appear on mobile dashboards but root cause
is ambiguous: the p95 wall time is 1 400 ms while the D1 query time
exported via `console.log` is only 80 ms. The missing ~1 300 ms is
invisible without trace context propagation that follows a request
from the mobile client through the edge Worker, into D1, and back.
Standard metrics show WHERE latency occurs; traces show WHY.

---

## Context

Cloudflare Workers run at the edge without a traditional APM agent.
Distributed tracing requires manual trace context propagation using
the W3C Trace Context standard (`traceparent` / `tracestate` headers).
D1 is Cloudflare's SQLite-at-the-edge database; queries run in the
same PoP as the Worker but are subject to replication lag and lock
contention that metrics alone cannot diagnose.

Mobile requests exhibit higher trace drop rates because LTE connections
are severed mid-request and the trace never receives a `span.end()`
call.

---

## W3C Trace Context Propagation in Workers

```typescript
// lib/trace.ts — lightweight trace context without an SDK dependency

export interface Span {
  traceId:  string;
  spanId:   string;
  parentId: string | null;
  name:     string;
  start:    number;
  end?:     number;
  attrs:    Record<string, string | number | boolean>;
}

export function newTraceId(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export function newSpanId(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
}

export function parseTraceparent(header: string | null): {
  traceId: string; parentId: string | null
} {
  if (!header) return { traceId: newTraceId(), parentId: null };
  const parts = header.split("-");
  // format: 00-{traceId}-{spanId}-{flags}
  if (parts.length !== 4 || parts[0] !== "00") {
    return { traceId: newTraceId(), parentId: null };
  }
  return { traceId: parts[1], parentId: parts[2] };
}

export function makeTraceparent(traceId: string, spanId: string): string {
  return `00-${traceId}-${spanId}-01`;
}
```

Usage in the main Worker fetch handler:

```typescript
import { parseTraceparent, makeTraceparent, newSpanId } from "./lib/trace";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { traceId, parentId } = parseTraceparent(
      request.headers.get("traceparent")
    );
    const rootSpanId = newSpanId();
    const spans: Span[] = [];

    const rootSpan: Span = {
      traceId, spanId: rootSpanId, parentId,
      name:  "workers.fetch",
      start: Date.now(),
      attrs: {
        "http.method":    request.method,
        "http.url":       request.url,
        "device.type":    request.cf?.deviceType ?? "unknown",
        "cf.country":     request.cf?.country ?? "XX",
        "cf.colo":        request.cf?.colo ?? "???",
      },
    };
    spans.push(rootSpan);

    // Propagate context to downstream fetch calls
    const downstreamHeaders = new Headers(request.headers);
    downstreamHeaders.set(
      "traceparent",
      makeTraceparent(traceId, rootSpanId)
    );

    const response = await routeRequest(request, env, {
      traceId, parentSpanId: rootSpanId, spans,
    });

    rootSpan.end = Date.now();
    rootSpan.attrs["http.status"] = response.status;

    // Non-blocking export — do not await inside the request path
    env.ctx.waitUntil(exportSpans(spans, env));

    return response;
  },
};
```

---

## D1 Query Span Instrumentation

Wrap every D1 call with a child span:

```typescript
async function d1Query<T>(
  db: D1Database,
  sql: string,
  params: unknown[],
  ctx: TraceContext,
): Promise<D1Result<T>> {
  const spanId = newSpanId();
  const start  = Date.now();

  const span: Span = {
    traceId:  ctx.traceId,
    spanId,
    parentId: ctx.parentSpanId,
    name:     "d1.query",
    start,
    attrs: {
      "db.system":    "sqlite",
      "db.statement": sql.slice(0, 200),   // truncate long queries
      "db.params":    JSON.stringify(params).slice(0, 100),
    },
  };

  try {
    const result = await db.prepare(sql).bind(...params).all<T>();
    span.end = Date.now();
    span.attrs["d1.rows_read"]     = result.meta.rows_read;
    span.attrs["d1.rows_written"]  = result.meta.rows_written;
    span.attrs["d1.duration_ms"]   = result.meta.duration;
    ctx.spans.push(span);
    return result;
  } catch (err) {
    span.end = Date.now();
    span.attrs["error"] = true;
    span.attrs["error.message"] = String(err);
    ctx.spans.push(span);
    throw err;
  }
}
```

---

## Span Export to Jaeger / OTLP

Export spans using the OTLP/HTTP protobuf endpoint of any
OpenTelemetry-compatible collector (Jaeger, Grafana Tempo, Honeycomb):

```typescript
async function exportSpans(spans: Span[], env: Env): Promise<void> {
  const payload = {
    resourceSpans: [{
      resource: {
        attributes: [
          { key: "service.name", value: { stringValue: "example project-api" } },
          { key: "deployment.environment",
            value: { stringValue: env.ENVIRONMENT } },
        ],
      },
      scopeSpans: [{
        spans: spans.map((s) => ({
          traceId:           s.traceId,
          spanId:            s.spanId,
          parentSpanId:      s.parentId ?? undefined,
          name:              s.name,
          startTimeUnixNano: String(s.start * 1_000_000),
          endTimeUnixNano:   String((s.end ?? s.start) * 1_000_000),
          attributes:        Object.entries(s.attrs).map(([k, v]) => ({
            key:   k,
            value: typeof v === "number"
              ? { doubleValue: v }
              : typeof v === "boolean"
                ? { boolValue: v }
                : { stringValue: String(v) },
          })),
        })),
      }],
    }],
  };

  await fetch(env.OTLP_ENDPOINT + "/v1/traces", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });
}
```

---

## Sampling Strategies for High-Volume Mobile Traffic

At 10 M mobile requests/day, exporting 100 % of spans costs ~$50/day
in Honeycomb ingestion alone. Use head-based sampling at the edge:

| Strategy              | Keep rate    | Use case                        |
|-----------------------|--------------|---------------------------------|
| Always sample errors  | 100 %        | Any span with error=true        |
| Mobile slow requests  | 100 %        | wall_ms > 1000 on mobile        |
| Random mobile sample  | 5 %          | Baseline coverage               |
| Random desktop sample | 20 %         | Baseline coverage               |
| Admin/internal IPs    | 100 %        | Debugging sessions              |

```typescript
function shouldSample(span: Span, isMobile: boolean): boolean {
  if (span.attrs["error"] === true)  return true;
  if (span.attrs["http.status"] >= 500) return true;
  const wallMs = span.attrs["http.status"] as number;
  if (isMobile && wallMs > 1000)     return true;
  return Math.random() < (isMobile ? 0.05 : 0.20);
}
```

---

## Trace Topology for example project Mobile Requests

```
Mobile Client
    │  traceparent: 00-<tid>-<sid>-01
    ▼
Cloudflare Edge (example project-pages)
    │  span: pages.asset / pages.ssr
    ▼
Cloudflare Worker (example project-api)
    ├── span: workers.fetch           [root]
    ├── span: auth.verify             [child]
    ├── span: d1.query (SELECT user)  [child]
    ├── span: d1.query (SELECT items) [child]
    └── span: kv.get (cache check)    [child]
```

Spans for D1 should show `d1.duration_ms` from the binding metadata
AND `wall_ms` from the Worker clock. The difference is network
overhead between the Worker isolate and the D1 replica — typically
< 2 ms intra-PoP but can spike to 30 ms+ during D1 replication events.

---

## Anti-Patterns

- Creating a new `traceId` for every Worker invocation. This breaks
  the trace for mobile clients that set `traceparent` in their fetch
  calls — always check the incoming header first.
- Awaiting span export inside the main request handler. `waitUntil()`
  is required to export after the response is sent.
- Storing raw SQL with user values in `db.statement` span attributes.
  Always parameterise queries AND truncate the logged statement.
- Sampling by dropping spans after the fact (tail sampling requires
  a stateful collector; Workers are stateless per invocation).

---

## Gotchas

- D1 `result.meta.duration` reports query execution time inside
  SQLite, not round-trip time. Add Worker-side clock measurements for
  the true latency a user experiences.
- `crypto.randomUUID()` is available in Workers but not in Miniflare
  v2. Tests using Miniflare < 3 need a polyfill.
- OTLP/HTTP endpoints behind Cloudflare Access require a service token
  in the `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers on
  the export fetch — easy to miss in local dev.
- `env.ctx.waitUntil()` has a maximum duration of 30 seconds. If the
  OTLP collector is slow, spans may be dropped silently.

---

## Verification

```bash
# Confirm traceparent flows through by echoing it from the API
curl -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  https://api.example project.example.com/ping | jq '.trace_id'

# Check Grafana Tempo for the trace
curl "http://tempo:3200/api/traces/4bf92f3577b34da6a3ce929d0e0e4736" \
  | jq '.batches[].scopeSpans[].spans[].name'
```

---

## Related

- documentation/docs/policies/monitoring/cloudflare-workers-tail-debugging.md
- documentation/docs/policies/monitoring/distributed-tracing-sampling-strategies.md
- documentation/docs/policies/monitoring/opentelemetry-custom-spans.md
- documentation/docs/policies/monitoring/w3c-trace-context-propagation.md
- documentation/docs/policies/monitoring/log-correlation-trace-context-propagation.md

---

## Source URLs

- https://developers.cloudflare.com/d1/observability/metrics-analytics/
- https://www.w3.org/TR/trace-context/
- https://opentelemetry.io/docs/specs/otlp/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://grafana.com/docs/tempo/latest/api_docs/
