# Sidecar Pattern for Logging and Tracing in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Every Worker in the system has hand-rolled `console.log` statements and duplicated telemetry code. Updating the log schema or adding trace propagation means touching every Worker. You want a dedicated sidecar Worker that absorbs all observability concerns — structured logging, trace-context propagation, error reporting — so domain Workers stay focused on business logic.

---

## Context

The sidecar pattern attaches a helper process alongside a primary process, sharing its lifecycle but handling cross-cutting concerns (logging, proxying, health-checks). In Cloudflare Workers, the equivalent is:

1. **Tail Workers** (`workers_dev.tail` / `logpush`): receive a stream of log events from any Worker invocation asynchronously. No latency added to the hot path.
2. **Service binding sidecar**: a sidecar Worker called synchronously (before or after business logic) for trace injection, request correlation, or audit logging.
3. **Workers Analytics Engine**: the sidecar writes structured events to Analytics Engine instead of `console.log`.

This article covers the combination: a service-binding sidecar for synchronous trace injection, and a Tail Worker for async log shipping.

```
Inbound Request
     │
     ▼
┌──────────────┐   service binding   ┌──────────────────┐
│ API Worker   │ ──────────────────► │ Telemetry Sidecar│ ──► Analytics Engine
│ (business)   │ ◄────────────────── │ (trace headers)  │
└──────────────┘                     └──────────────────┘
     │  tail                                  ▲
     ▼                                        │
┌──────────────┐                     ┌──────────────────┐
│ Tail Worker  │ ──────────────────► │  Log Aggregator  │
│ (async)      │                     │  (Logpush / SIEM)│
└──────────────┘                     └──────────────────┘
```

---

## Trace Context Propagation (W3C TraceContext)

```typescript
// telemetry-sidecar/src/trace.ts
export interface TraceContext {
  traceId: string;   // 32 hex chars
  spanId: string;    // 16 hex chars
  sampled: boolean;
}

function hex(bytes: number): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(bytes)))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

export function extractOrCreate(headers: Headers): TraceContext {
  const traceparent = headers.get('traceparent');
  if (traceparent) {
    // W3C format: 00-{traceId}-{parentSpanId}-{flags}
    const parts = traceparent.split('-');
    if (parts.length === 4) {
      return {
        traceId: parts[1],
        spanId: hex(8),         // new child span
        sampled: parts[3] === '01',
      };
    }
  }
  return { traceId: hex(16), spanId: hex(8), sampled: Math.random() < 0.1 };
}

export function buildTraceparent(ctx: TraceContext): string {
  return `00-${ctx.traceId}-${ctx.spanId}-${ctx.sampled ? '01' : '00'}`;
}
```

---

## Telemetry Sidecar Worker

```typescript
// telemetry-sidecar/src/index.ts
import { Env } from './types';
import { extractOrCreate, buildTraceparent, TraceContext } from './trace';

interface EnrichRequest {
  method: string;
  url: string;
  cfRay: string | null;
  headers: Record<string, string>;
}

interface EnrichResponse {
  traceparent: string;
  traceId: string;
  spanId: string;
  sampled: boolean;
  requestId: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json() as EnrichRequest;
    const inboundHeaders = new Headers(body.headers);

    const ctx: TraceContext = extractOrCreate(inboundHeaders);
    const requestId = crypto.randomUUID();

    // Write structured event to Analytics Engine (non-blocking)
    env.ANALYTICS.writeDataPoint({
      blobs: [body.method, body.url, body.cfRay ?? '', ctx.traceId, requestId],
      doubles: [Date.now()],
      indexes: [ctx.traceId],
    });

    const response: EnrichResponse = {
      traceparent: buildTraceparent(ctx),
      traceId: ctx.traceId,
      spanId: ctx.spanId,
      sampled: ctx.sampled,
      requestId,
    };

    return Response.json(response);
  },
};
```

---

## API Worker — Calling the Sidecar

```typescript
// api-worker/src/index.ts
import { Env } from './types';

async function withTelemetry(
  request: Request,
  env: Env
): Promise<{ request: Request; traceId: string; requestId: string }> {
  const enrichReq = new Request('https://telemetry/enrich', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      method: request.method,
      url: request.url,
      cfRay: request.headers.get('CF-Ray'),
      headers: Object.fromEntries(request.headers.entries()),
    }),
  });

  const enrichRes = await env.TELEMETRY_SVC.fetch(enrichReq);
  const { traceparent, traceId, requestId } = await enrichRes.json() as {
    traceparent: string; traceId: string; requestId: string;
  };

  // Clone request with trace headers injected for downstream calls
  const enrichedRequest = new Request(request, {
    headers: new Headers({
      ...Object.fromEntries(request.headers.entries()),
      traceparent,
      'x-request-id': requestId,
    }),
  });

  return { request: enrichedRequest, traceId, requestId };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { request: enriched, traceId, requestId } = await withTelemetry(request, env);

    try {
      // Business logic
      const data = await env.DB.prepare('SELECT * FROM products LIMIT 10').all();
      const response = Response.json({ data: data.results });
      response.headers.set('X-Trace-Id', traceId);
      response.headers.set('X-Request-Id', requestId);
      return response;
    } catch (err) {
      console.error(JSON.stringify({ traceId, requestId, error: String(err) }));
      return new Response('Internal Server Error', { status: 500 });
    }
  },
};
```

---

## Tail Worker for Async Log Shipping

```typescript
// tail-worker/src/index.ts
// Declared in wrangler.toml via `tail_consumers`
import { Env } from './types';

interface StructuredLog {
  traceId: string | null;
  requestId: string | null;
  workerName: string;
  outcome: string;
  durationMs: number;
  errors: string[];
  timestamp: string;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    const logs: StructuredLog[] = events.map(event => ({
      traceId: event.logs
        .find(l => typeof l.message?.[0] === 'object' && (l.message[0] as Record<string, unknown>)['traceId'])
        ?.message?.[0] as string | null ?? null,
      requestId: null,
      workerName: event.scriptName ?? 'unknown',
      outcome: event.outcome,
      durationMs: event.eventTimestamp,
      errors: event.exceptions.map(e => `${e.name}: ${e.message}`),
      timestamp: new Date(event.eventTimestamp).toISOString(),
    }));

    // Batch ship to external SIEM / log aggregator
    await fetch(env.LOG_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.LOG_TOKEN}`,
      },
      body: JSON.stringify(logs),
    });
  },
};
```

---

## Wrangler Configuration

```toml
# api-worker/wrangler.toml
name = "api-worker"

[[services]]
binding = "TELEMETRY_SVC"
service = "telemetry-sidecar"

[[tail_consumers]]
service = "tail-worker"

# telemetry-sidecar/wrangler.toml
name = "telemetry-sidecar"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "request_telemetry"
```

---

## Anti-patterns

- **Synchronous logging on the hot path**: writing to an external logging API inside the domain Worker's `fetch` handler adds latency to every request. Use the Tail Worker for async shipping.
- **Coupling trace ID generation to business logic**: the domain Worker should not generate trace IDs. That is the sidecar's responsibility; the Worker only propagates what it receives.
- **One big log blob**: `console.log(JSON.stringify(everythingAsOneObject))` makes downstream parsing brittle. Emit structured, typed log lines keyed by `level`, `traceId`, and `event`.
- **Sidecar with business logic**: the sidecar must not make business decisions (e.g. reject a request based on trace sampling). It enriches; it does not gate.

---

## Gotchas

- The `tail` handler runs **after** the main Worker invocation completes. It has a separate CPU budget. Avoid heavy computation; its job is shipping, not processing.
- Tail Workers only receive logs from Workers **in the same account**. Third-party service calls are invisible unless you explicitly log their responses.
- Analytics Engine `writeDataPoint` is fire-and-forget; errors are not surfaced to the calling Worker.
- Service binding calls to the sidecar consume subrequests. If every API endpoint calls the sidecar, budget consumption doubles for those endpoints.
- `TraceItem` is a Workers-specific type; import it from `@cloudflare/workers-types` — it is not in the standard lib.

---

## Verification

```bash
# Confirm trace headers reach downstream
curl -v https://api.example.com/products | grep -i 'x-trace-id'

# Stream tail worker logs to confirm log shipping
wrangler tail tail-worker

# Query Analytics Engine for request telemetry
wrangler analytics engine query request_telemetry \
  --sql "SELECT blob1 AS method, blob2 AS url, COUNT(*) FROM request_telemetry WHERE timestamp > NOW() - INTERVAL '1' HOUR GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10"
```

---

## Related

- `sidecar-pattern.md`
- `distributed-tracing-architecture.md`
- `observability-architecture.md`
- `workers-tail-handlers-observability.md`
- `analytics-engine-event-pipeline.md`

---

## Sources

- Cloudflare Workers Tail Workers — https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- W3C TraceContext specification — https://www.w3.org/TR/trace-context/
- Sidecar pattern (Azure Architecture Center) — https://learn.microsoft.com/en-us/azure/architecture/patterns/sidecar
