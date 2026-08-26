# W3C Trace Context Propagation Across Workers Service Bindings

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application spans multiple Workers connected via service bindings and you need end-to-end distributed traces: a single `traceparent` header flows from the edge Worker through every downstream service binding call, each Worker writes its span to D1, and a trace-viewer endpoint reconstructs the full call tree for debugging latency and errors.

## Context

- W3C Trace Context spec (traceparent / tracestate headers)
- Workers service bindings (same-account, zero-egress RPC)
- D1 stores spans: trace_id, span_id, parent_span_id, service, duration, status
- A trace-viewer Worker endpoint queries D1 and returns a nested span tree
- Stack: Workers (TypeScript), D1, service bindings, Wrangler 3.x

---

## Step 1 — D1 Span Storage Schema

```sql
-- migrations/0001_spans.sql
CREATE TABLE IF NOT EXISTS spans (
  span_id       TEXT    PRIMARY KEY,
  trace_id      TEXT    NOT NULL,
  parent_span_id TEXT,
  service       TEXT    NOT NULL,
  operation     TEXT    NOT NULL,
  start_time    TEXT    NOT NULL,   -- ISO-8601 with ms precision
  duration_ms   INTEGER NOT NULL,
  status_code   INTEGER NOT NULL,
  error_message TEXT,
  attributes    TEXT                -- JSON blob of key-value pairs
);

CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans (trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_start    ON spans (start_time DESC);
```

```bash
wrangler d1 create tracing-db
wrangler d1 migrations apply tracing-db --remote
```

## Step 2 — Trace Context Utilities

```typescript
// src/trace-context.ts

export interface TraceContext {
  traceId:      string;  // 32 hex chars
  spanId:       string;  // 16 hex chars
  parentSpanId: string | null;
  sampled:      boolean;
}

/** Parse W3C traceparent header: '00-<traceId>-<spanId>-<flags>' */
export function parseTraceparent(header: string | null): TraceContext | null {
  if (!header) return null;
  const parts = header.split('-');
  if (parts.length < 4 || parts[0] !== '00') return null;
  const [, traceId, spanId, flags] = parts;
  if (traceId.length !== 32 || spanId.length !== 16) return null;
  return {
    traceId,
    spanId,       // this is the PARENT span from the caller's perspective
    parentSpanId: spanId,
    sampled:      (parseInt(flags, 16) & 1) === 1,
  };
}

/** Generate a new traceparent for an outgoing call (new span child of parent) */
export function newTraceparent(
  traceId: string,
  newSpanId: string,
  sampled = true
): string {
  const flags = sampled ? '01' : '00';
  return `00-${traceId}-${newSpanId}-${flags}`;
}

/** Generate a root traceparent when no upstream context exists */
export function newRootTraceparent(): { traceparent: string; context: TraceContext } {
  const traceId = crypto.randomUUID().replace(/-/g, '');
  const spanId  = crypto.randomUUID().replace(/-/g, '').slice(0, 16);
  const traceparent = newTraceparent(traceId, spanId);
  return {
    traceparent,
    context: { traceId, spanId, parentSpanId: null, sampled: true },
  };
}

/** Generate a child span ID */
export function newChildSpanId(): string {
  return crypto.randomUUID().replace(/-/g, '').slice(0, 16);
}
```

## Step 3 — Span Recording Helper

```typescript
// src/span-recorder.ts
import { TraceContext } from './trace-context';

export interface SpanOptions {
  service:   string;
  operation: string;
  attributes?: Record<string, string | number | boolean>;
}

export interface Span {
  spanId:       string;
  traceparent:  string;  // to pass to downstream calls
  finish(statusCode: number, errorMessage?: string): Promise<void>;
}

export function startSpan(
  db: D1Database,
  context: TraceContext,
  childSpanId: string,
  opts: SpanOptions
): Span {
  const startTime = new Date().toISOString();
  const startMs   = Date.now();

  // Build the traceparent for any downstream call this span makes
  const childTraceparent =
    `00-${context.traceId}-${childSpanId}-${context.sampled ? '01' : '00'}`;

  return {
    spanId: childSpanId,
    traceparent: childTraceparent,

    async finish(statusCode: number, errorMessage?: string): Promise<void> {
      const durationMs = Date.now() - startMs;
      await db
        .prepare(
          `INSERT INTO spans
             (span_id, trace_id, parent_span_id, service, operation,
              start_time, duration_ms, status_code, error_message, attributes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
        )
        .bind(
          childSpanId,
          context.traceId,
          context.parentSpanId,
          opts.service,
          opts.operation,
          startTime,
          durationMs,
          statusCode,
          errorMessage ?? null,
          opts.attributes ? JSON.stringify(opts.attributes) : null
        )
        .run();
    },
  };
}
```

## Step 4 — Edge Worker (Entry Point)

```typescript
// src/edge-worker.ts
import { parseTraceparent, newRootTraceparent, newChildSpanId } from './trace-context';
import { startSpan } from './span-recorder';

interface Env {
  DB:      D1Database;
  API_SVC: Fetcher;  // service binding to downstream Worker
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Resolve or create trace context
    let traceId: string;
    let parentSpanId: string | null;
    let inboundTraceparent = request.headers.get('traceparent');

    const upstream = parseTraceparent(inboundTraceparent);
    if (upstream) {
      traceId      = upstream.traceId;
      parentSpanId = upstream.spanId;
    } else {
      const root = newRootTraceparent();
      inboundTraceparent = root.traceparent;
      traceId      = root.context.traceId;
      parentSpanId = null;
    }

    const mySpanId = newChildSpanId();
    const span = startSpan(
      env.DB,
      { traceId, spanId: parentSpanId ?? mySpanId, parentSpanId, sampled: true },
      mySpanId,
      { service: 'edge-worker', operation: `${request.method} ${new URL(request.url).pathname}` }
    );

    // Forward request to downstream service binding, injecting child traceparent
    const downstreamHeaders = new Headers(request.headers);
    downstreamHeaders.set('traceparent', span.traceparent);

    let response: Response;
    try {
      response = await env.API_SVC.fetch(
        new Request(request.url, { ...request, headers: downstreamHeaders })
      );
      await span.finish(response.status);
    } catch (err) {
      await span.finish(500, String(err));
      throw err;
    }

    // Surface trace-id in response header for client debugging
    const out = new Response(response.body, response);
    out.headers.set('x-trace-id', traceId);
    return out;
  },
};
```

## Step 5 — Trace Viewer Endpoint

```typescript
// src/trace-viewer.ts  (mounted at /traces/:traceId in a fetch handler)
export async function handleTraceView(traceId: string, db: D1Database): Promise<Response> {
  if (!/^[0-9a-f]{32}$/.test(traceId)) {
    return Response.json({ error: 'invalid trace id' }, { status: 400 });
  }

  const rows = await db
    .prepare(
      `SELECT span_id, parent_span_id, service, operation,
              start_time, duration_ms, status_code, error_message, attributes
       FROM spans
       WHERE trace_id = ?
       ORDER BY start_time ASC
       LIMIT 200`
    )
    .bind(traceId)
    .all<{
      span_id: string; parent_span_id: string | null; service: string;
      operation: string; start_time: string; duration_ms: number;
      status_code: number; error_message: string | null; attributes: string | null;
    }>();

  if (!rows.results.length) {
    return Response.json({ error: 'trace not found' }, { status: 404 });
  }

  // Build tree
  type SpanNode = typeof rows.results[0] & { children: SpanNode[] };
  const byId = new Map<string, SpanNode>();
  for (const r of rows.results) byId.set(r.span_id, { ...r, children: [] });

  const roots: SpanNode[] = [];
  for (const node of byId.values()) {
    if (node.parent_span_id && byId.has(node.parent_span_id)) {
      byId.get(node.parent_span_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }

  return Response.json({ trace_id: traceId, spans: roots });
}
```

## Anti-patterns

- Generating a new trace ID at every service boundary — breaks the trace; only generate a root trace ID once at the edge, propagate it unchanged
- Storing spans synchronously on the critical path without `ctx.waitUntil` — adds D1 write latency to every request; wrap span `finish()` in `ctx.waitUntil(span.finish(...))`
- Sampling 100% of traces in production at high traffic — D1 will fill quickly; implement head-based sampling via the `sampled` flag and only write spans when `context.sampled === true`
- Passing tracestate across trust boundaries without stripping vendor-specific entries — scrub unknown `tracestate` vendors at the edge

## Gotchas

- Service bindings do NOT automatically propagate request headers; you must manually copy `traceparent` onto the outgoing `Request` headers object
- `crypto.randomUUID()` returns a UUID with dashes; strip them to produce the 32-char hex trace ID required by W3C spec
- D1 has a 1 MB per-row limit; keep `attributes` JSON small — store only indexable dimensions, not full request bodies
- `ctx.waitUntil` must be called before the Response is returned; you cannot call it in a `finally` block after `return response`
- W3C specifies the `traceparent` version field as `00`; future versions may change the format — the parser validates this

## Verification

```bash
# Make a request and capture the returned trace ID
TRACE_ID=$(curl -s -D - https://edge-worker.<subdomain>.workers.dev/api/test \
  | grep -i x-trace-id | awk '{print $2}' | tr -d '\r')

echo "Trace ID: $TRACE_ID"

# Query the trace viewer
curl -s "https://trace-viewer.<subdomain>.workers.dev/traces/$TRACE_ID" | jq .

# Inspect D1 directly
wrangler d1 execute tracing-db --remote \
  --command "SELECT service, operation, duration_ms, status_code FROM spans WHERE trace_id='$TRACE_ID' ORDER BY start_time;"

# Count spans per service in last hour
wrangler d1 execute tracing-db --remote \
  --command "SELECT service, COUNT(*) FROM spans WHERE start_time >= datetime('now','-1 hour') GROUP BY service;"
```

## Related

- `documentation/docs/policies/monitoring/workers-logpush-structured-event-pipeline.md`
- `documentation/docs/policies/monitoring/workers-health-check-dashboard-d1-kv.md`

## Sources

- https://www.w3.org/TR/trace-context/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
