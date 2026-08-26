# Distributed Trace Context Propagation Through Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Requests flowing through multiple Cloudflare Workers (edge gateway -> service bindings -> origin) lose context between hops. You need end-to-end trace IDs so you can correlate logs, measure per-service latency, and export span data to a tracing backend — all without a sidecar proxy.

## Context

The W3C Trace Context specification defines the `traceparent` header as the standard propagation carrier. Format: `00-{trace-id}-{parent-span-id}-{flags}`. Workers can parse and forward this header, generate new span IDs per hop, and export completed spans via Tail Workers. Service Bindings allow zero-latency calls between Workers in the same account; trace context must be explicitly forwarded in those calls. Sampling decisions encoded in the `traceflags` byte must also propagate to avoid head-based sampling inconsistency.

## Solution

### Trace context types and parser

```typescript
// src/trace.ts

export interface TraceContext {
  traceId: string;    // 16-byte hex (32 chars)
  parentId: string;   // 8-byte hex (16 chars)
  sampled: boolean;
}

const TRACEPARENT_RE =
  /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/i;

export function parseTraceparent(header: string | null): TraceContext | null {
  if (!header) return null;
  const m = header.match(TRACEPARENT_RE);
  if (!m) return null;
  return {
    traceId:  m[1].toLowerCase(),
    parentId: m[2].toLowerCase(),
    sampled:  (parseInt(m[3], 16) & 0x01) === 1,
  };
}

export function formatTraceparent(ctx: TraceContext): string {
  const flags = ctx.sampled ? '01' : '00';
  return `00-${ctx.traceId}-${ctx.parentId}-${flags}`;
}

export async function generateTraceId(): Promise<string> {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function generateSpanId(): Promise<string> {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

// Head-based sampling: sample 10% of new traces
export function shouldSample(sampleRate = 0.1): boolean {
  return Math.random() < sampleRate;
}

// Create or inherit a trace context from an incoming request
export async function resolveTraceContext(
  request: Request,
  sampleRate = 0.1
): Promise<TraceContext> {
  const incoming = parseTraceparent(request.headers.get('traceparent'));
  if (incoming) {
    // Inherit trace ID and sampling decision from upstream
    return {
      traceId: incoming.traceId,
      parentId: await generateSpanId(), // New span for this hop
      sampled: incoming.sampled,
    };
  }
  // Root span: generate a new trace
  return {
    traceId: await generateTraceId(),
    parentId: await generateSpanId(),
    sampled: shouldSample(sampleRate),
  };
}
```

### Span data model and collector

```typescript
// src/span.ts

import type { TraceContext } from './trace';

export interface Span {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  service: string;
  startMs: number;
  endMs: number;
  attributes: Record<string, string | number | boolean>;
  status: 'ok' | 'error';
  errorMessage?: string;
}

export class SpanCollector {
  private spans: Span[] = [];
  private traceCtx: TraceContext;

  constructor(traceCtx: TraceContext) {
    this.traceCtx = traceCtx;
  }

  startSpan(
    name: string,
    service: string,
    parentSpanId?: string
  ): { spanId: string; startMs: number } {
    const spanId  = this.traceCtx.parentId; // reuse resolved span id
    const startMs = Date.now();
    return { spanId, startMs };
  }

  endSpan(
    name: string,
    service: string,
    startMs: number,
    spanId: string,
    attributes: Span['attributes'] = {},
    status: Span['status'] = 'ok',
    errorMessage?: string
  ) {
    if (!this.traceCtx.sampled) return;
    this.spans.push({
      traceId: this.traceCtx.traceId,
      spanId,
      name,
      service,
      startMs,
      endMs: Date.now(),
      attributes,
      status,
      errorMessage,
    });
  }

  collect(): Span[] {
    return this.spans;
  }
}
```

### Forwarding trace context through service bindings

```typescript
// src/gateway.ts

import { resolveTraceContext, formatTraceparent, generateSpanId } from './trace';
import { SpanCollector } from './span';

interface Env {
  DOWNSTREAM_SERVICE: Fetcher; // service binding
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const traceCtx   = await resolveTraceContext(request);
    const collector  = new SpanCollector(traceCtx);
    const start      = Date.now();
    const spanId     = await generateSpanId();

    // Build outbound request with updated traceparent
    // The parentId for the downstream call is a new span ID
    const downstreamTraceCtx = {
      ...traceCtx,
      parentId: spanId,
    };

    const outboundHeaders = new Headers(request.headers);
    outboundHeaders.set('traceparent', formatTraceparent(downstreamTraceCtx));
    // Propagate baggage if present
    const baggage = request.headers.get('baggage');
    if (baggage) outboundHeaders.set('baggage', baggage);

    let response: Response;
    let status: 'ok' | 'error' = 'ok';
    let errorMessage: string | undefined;
    try {
      response = await env.DOWNSTREAM_SERVICE.fetch(
        new Request(request.url, { ...request, headers: outboundHeaders })
      );
      if (response.status >= 500) {
        status = 'error';
        errorMessage = `downstream status ${response.status}`;
      }
    } catch (err) {
      status = 'error';
      errorMessage = err instanceof Error ? err.message : 'unknown';
      response = new Response('Service unavailable', { status: 503 });
    }

    collector.endSpan(
      'downstream.fetch',
      'gateway',
      start,
      spanId,
      { 'http.status_code': response.status, 'http.url': request.url },
      status,
      errorMessage
    );

    // Export spans via waitUntil so it doesn't block response
    ctx.waitUntil(exportSpans(collector.collect()));

    return response;
  },
} satisfies ExportedHandler<Env>;

async function exportSpans(spans: import('./span').Span[]) {
  if (spans.length === 0) return;
  // Export to your OTLP HTTP endpoint or Analytics Engine
  await fetch('https://otel-collector.example.com/v1/traces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spans }),
  });
}
```

### Tail Worker for passive trace export

```typescript
// src/tail.ts — wrangler.toml: tail_consumers = [{service = "trace-exporter"}]

export default {
  async tail(events: TraceItem[], _env: unknown, _ctx: ExecutionContext) {
    for (const event of events) {
      const traceparent = event.request?.headers?.find(
        ([k]) => k.toLowerCase() === 'traceparent'
      )?.[1];
      if (!traceparent) continue;

      // Parse and forward to trace backend
      console.log(JSON.stringify({
        type: 'tail-trace',
        traceparent,
        outcome: event.outcome,
        durationMs: event.eventTimestamp
          ? Date.now() - event.eventTimestamp
          : null,
        scriptName: event.scriptName,
        logs: event.logs.map(l => ({ level: l.level, message: l.message })),
      }));
    }
  },
} satisfies ExportedHandler;
```

### wrangler.toml for tail consumer

```toml
[[tail_consumers]]
service = "trace-tail-worker"
```

## Implementation Details

- **Span ID per hop**: Each Worker generates a new `spanId` for its own work. The incoming `parentId` identifies the calling span. This creates a parent-child chain reconstructible in any tracing UI.
- **Sampling consistency**: Always inherit the `sampled` flag from the incoming `traceparent`. Never re-roll sampling for an existing trace. Only generate a new sampling decision when creating a root span.
- **Web Crypto availability**: `crypto.getRandomValues` is available in all Workers without any compatibility flags. Do not use `Math.random()` for trace/span IDs.
- **Baggage propagation**: The W3C Baggage header (`baggage`) carries key-value metadata (e.g. `tenant-id=abc,env=prod`). Forward it alongside `traceparent` to all downstream calls.

## Anti-patterns

- **Generating a new trace ID on every hop**: This breaks the trace chain. A new trace ID must only be generated when no incoming `traceparent` is present.
- **Mutating the incoming Request directly**: `Request` is immutable in Workers. Always construct a `new Headers(request.headers)` copy before adding trace headers.
- **Exporting spans synchronously on the request path**: Span export to external systems should always be deferred to `ctx.waitUntil`.
- **Using `Date.now()` drift**: For sub-millisecond precision, use `performance.now()` to measure duration within a single Worker invocation, converting to wall time via `Date.now()` at span start.

## Gotchas

- Service Binding calls do not automatically forward headers. You must explicitly copy and set `traceparent` on the outbound `Request`.
- `TraceItem.eventTimestamp` in Tail Workers is in Unix seconds (not milliseconds) in some runtime versions. Verify the unit against the actual value.
- The `traceparent` version field is currently always `00`. A parser must reject headers with unsupported versions per the W3C spec.
- Cloudflare's own tracing (Trace v2) uses a separate system. This guide covers application-level W3C propagation, not Cloudflare's network trace.

## Verification

```bash
# Send a request with a traceparent and verify it propagates
curl -v https://your-gateway.example.com/api/test \
  -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'

# Check logs for the downstream service to confirm the trace ID matches
```

## Related

- `documentation/categories/monitoring/workers-structured-logging-analytics-engine.md`
- `documentation/categories/monitoring/workers-anomaly-detection-analytics-engine.md`

## Sources

- https://www.w3.org/TR/trace-context/
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://opentelemetry.io/docs/specs/otel/protocol/exporter/
