# Tail Worker OpenTelemetry Span Export

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Distributed traces must be assembled from Cloudflare Workers without adding any latency to the critical request path. A Tail Worker receives finished invocation telemetry asynchronously and can forward structured OTLP spans to any compatible backend.

## Context
Tail Workers are invoked after the observed Worker finishes; they receive a `TailEvent` containing timing, outcome, exceptions, and logs for each invocation. By mapping `TailEvent` fields to the OTLP `ExportTraceServiceRequest` protobuf (sent as JSON over OTLP/HTTP), you get zero-latency-overhead distributed tracing that integrates with Grafana Tempo, Honeycomb, or any OTLP-compatible backend. Trace continuity relies on the observed Worker propagating a `traceparent` header in its logs.

## Tail Worker Registration

```jsonc
// wrangler.toml
name = "otel-tail-exporter"

[[tail_consumers]]
service = "my-api-worker"   # the Worker being observed
```

The Tail Worker itself needs no `routes`; it is triggered by the platform, not HTTP clients.

## Mapping TailEvent to OTLP Spans

```typescript
// src/tail-otel.ts
interface Env {
  OTLP_ENDPOINT: string;   // e.g. https://tempo.example.com/otlp/v1/traces
  OTLP_TOKEN:    string;
}

function hexId(bytes: number): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return Array.from(arr).map(b => b.toString(16).padStart(2, '0')).join('');
}

function extractTraceContext(event: TailerEvent): { traceId: string; parentSpanId: string | null } {
  // The observed Worker logs its own traceparent header in structured JSON
  for (const log of event.logs) {
    try {
      const parsed = JSON.parse(log.message[0] as string);
      if (parsed.traceparent) {
        const parts = (parsed.traceparent as string).split('-');
        return { traceId: parts[1], parentSpanId: parts[2] };
      }
    } catch { /* not JSON */ }
  }
  return { traceId: hexId(16), parentSpanId: null };
}

function tailEventToOtlpSpan(event: TailerEvent) {
  const { traceId, parentSpanId } = extractTraceContext(event);
  const spanId = hexId(8);
  const startNs = BigInt(event.eventTimestamp) * 1_000_000n;          // ms → ns
  const endNs   = startNs + BigInt(event.wallTimeUs ?? 0) * 1_000n;   // µs → ns

  const attributes = [
    { key: 'cf.worker.script_name', value: { stringValue: event.scriptName ?? '' } },
    { key: 'cf.worker.outcome',     value: { stringValue: event.outcome } },
    { key: 'cf.worker.cpu_time_us', value: { intValue: String(event.cpuTime ?? 0) } },
    { key: 'http.status_code',      value: { intValue: String(event.event?.response?.status ?? 0) } },
    { key: 'http.method',           value: { stringValue: event.event?.request?.method ?? '' } },
    { key: 'http.url',              value: { stringValue: event.event?.request?.url ?? '' } },
  ];

  if (event.exceptions.length > 0) {
    attributes.push({
      key: 'exception.message',
      value: { stringValue: event.exceptions.map(e => e.message).join('; ') },
    });
  }

  return {
    traceId,
    spanId,
    parentSpanId: parentSpanId ?? undefined,
    name: `${event.event?.request?.method ?? 'WORKER'} ${new URL(event.event?.request?.url ?? 'about:blank').pathname}`,
    kind: 2, // SPAN_KIND_SERVER
    startTimeUnixNano: String(startNs),
    endTimeUnixNano:   String(endNs),
    attributes,
    status: {
      code: event.outcome === 'ok' ? 1 : 2,
      message: event.outcome,
    },
  };
}
```

## Batching and Export

```typescript
// src/index.ts
import { tailEventToOtlpSpan } from './tail-otel';

export default {
  async tail(events: TailerEvent[], env: Env, ctx: ExecutionContext): Promise<void> {
    const spans = events.map(tailEventToOtlpSpan);

    const body = JSON.stringify({
      resourceSpans: [
        {
          resource: {
            attributes: [
              { key: 'service.name',    value: { stringValue: 'cloudflare-workers' } },
              { key: 'service.version', value: { stringValue: '1.0.0' } },
              { key: 'cloud.provider',  value: { stringValue: 'cloudflare' } },
            ],
          },
          scopeSpans: [
            {
              scope: { name: 'tail-worker-otel', version: '1.0.0' },
              spans,
            },
          ],
        },
      ],
    });

    ctx.waitUntil(
      fetch(`${env.OTLP_ENDPOINT}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization:  `Bearer ${env.OTLP_TOKEN}`,
        },
        body,
      }).then(r => {
        if (!r.ok) console.error('OTLP export failed', r.status, r.statusText);
      })
    );
  },
} satisfies ExportedHandler<Env>;
```

## Propagating traceparent from the Observed Worker

```typescript
// src/observed-worker.ts — the Worker being tailed
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Accept upstream traceparent or generate a new root trace
    const incoming = req.headers.get('traceparent');
    const traceId  = incoming ? incoming.split('-')[1] : crypto.randomUUID().replace(/-/g, '');
    const spanId   = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                       .map(b => b.toString(16).padStart(2, '0')).join('');
    const traceparent = `00-${traceId}-${spanId}-01`;

    // Emit traceparent in a structured log line so Tail Worker can extract it
    console.log(JSON.stringify({ traceparent, requestId: req.headers.get('cf-ray') }));

    const response = await handleRequest(req, env);

    // Forward traceparent downstream to fetch calls
    return new Response(response.body, {
      status:  response.status,
      headers: { ...Object.fromEntries(response.headers), traceparent },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns
- Calling `fetch` inside the Tail Worker outside of `ctx.waitUntil` — the runtime may terminate the Worker before export completes
- Exporting one HTTP request per event instead of batching the full `events` array — adds unnecessary egress and latency
- Hard-coding the OTLP endpoint URL in source — store it in a Worker Secret so it can rotate without redeployment
- Logging the full request/response body in the observed Worker for trace correlation — use only the traceparent header and structured IDs

## Gotchas
- `event.wallTimeUs` is the wall-clock duration in microseconds; CPU time (`event.cpuTime`) is separate and typically lower
- Tail Workers receive events in batches of up to 100; very high-traffic Workers will batch events, so iterate the full `events` array
- The Tail Worker itself can be tailed by another Tail Worker, but circular tailing is not supported
- `event.eventTimestamp` is in milliseconds; convert to nanoseconds for OTLP timestamps

## Verification
1. Deploy both Workers and send a test request: `curl -v https://my-worker.example.workers.dev/ping`
2. Query Grafana Tempo or Honeycomb within 30 s for traces tagged `service.name=cloudflare-workers`
3. Verify the span's `startTimeUnixNano` aligns with the wall clock within 5 s
4. Trigger a Worker exception; confirm the OTLP span `status.code` is 2 and `exception.message` is populated

## Related
- [workers-tail-real-time-log-streaming.md](workers-tail-real-time-log-streaming.md)
- [workers-tail-worker-pii-minimization-and-otel-decision.md](workers-tail-worker-pii-minimization-and-otel-decision.md)
- [opentelemetry-distributed-tracing-workers.md](opentelemetry-distributed-tracing-workers.md)
- [distributed-tracing-workers-d1-durable-objects-otel.md](distributed-tracing-workers-d1-durable-objects-otel.md)

## Sources
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://opentelemetry.io/docs/specs/otlp/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/
