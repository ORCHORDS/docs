# feature-observability-tracing

**Issue:** Distributed tracing — OpenTelemetry, span, context
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user reports "the page is slow." You look at the logs.
"GET /api/users 200 in 1.5s." You don't know WHERE the
1.5s went. DB? Vendor? Your code? You wish you had
traces.

## Root cause
**Logs don't show the request flow.** For multi-service
apps, you need distributed tracing.

**Source:** OpenTelemetry:
https://opentelemetry.io/

> "Distributed tracing is the process of tracking the
> progression of a single request ... as it traverses
> through multiple services."

## The "trace" concept

A **trace** is a tree of **spans**:
- **Trace:** The whole request (one trace ID)
- **Span:** A unit of work (one operation)
- **Parent span:** The containing operation
- **Child span:** A sub-operation

```
GET /api/users (trace=abc, span=1, 1500ms)
  ├─ db.query (trace=abc, span=2, 800ms)
  ├─ stripe.api (trace=abc, span=3, 600ms)
  └─ serialize (trace=abc, span=4, 100ms)
```

Each span has a name, start time, duration, and attributes.

## The "OpenTelemetry" pattern

```ts
import { trace, SpanStatusCode } from '@opentelemetry/api';

const tracer = trace.getTracer('my-app');

async function handleRequest(request: Request, env: Env): Promise<Response> {
  const span = tracer.startSpan('handleRequest', {
    attributes: {
      'http.method': request.method,
      'http.url': request.url,
    },
  });

  try {
    const result = await doWork(request, env);
    span.setAttribute('http.status_code', result.status);
    return result;
  } catch (err) {
    span.recordException(err as Error);
    span.setStatus({ code: SpanStatusCode.ERROR });
    throw err;
  } finally {
    span.end();
  }
}

async function doWork(request: Request, env: Env): Promise<Response> {
  const dbSpan = tracer.startSpan('db.query');
  try {
    const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind('u_123').first();
    dbSpan.setAttribute('db.user.id', 'u_123');
    return new Response(JSON.stringify(user));
  } finally {
    dbSpan.end();
  }
}
```

The spans are nested; the trace shows the full request.

## The "context propagation" pattern

For multi-service, the trace context is propagated:
```ts
// In the producer
const headers = {
  'X-Trace-Context': JSON.stringify({
    traceId: span.spanContext().traceId,
    spanId: span.spanContext().spanId,
  }),
};

await fetch('https://other-service/api', { headers });

// In the consumer
const traceContext = JSON.parse(request.headers.get('X-Trace-Context') ?? '{}');
// Continue the trace
const childSpan = tracer.startSpan('otherService', { links: [{ context: traceContext }] });
```

The trace is propagated via headers.

## The "CF Workers + OpenTelemetry" pattern

For CF Workers, the OpenTelemetry SDK is available:
```ts
import { trace } from '@opentelemetry/api';

// Workers auto-instrument many things
// You can add custom spans

const span = trace.getActiveSpan();
span?.setAttribute('user.id', ctx.user.id);
```

CF has a built-in OTel integration.

## The "span attributes" pattern

Add attributes to a span for context:
```ts
span.setAttribute('http.method', 'GET');
span.setAttribute('http.status_code', 200);
span.setAttribute('user.id', 'u_123');
span.setAttribute('tenant.id', 't_123');
span.setAttribute('feature.name', 'new-dashboard');
```

Attributes are searchable in the trace backend.

## The "span events" pattern

For specific events within a span:
```ts
span.addEvent('cache.miss', { key: 'user:123' });
span.addEvent('db.query.start');
span.addEvent('db.query.end', { duration: 100 });
```

Events are timestamps within the span.

## The "sampling" pattern

For high-traffic apps, sample:
```ts
// Sample 10% of traces
const sampler = new TraceIdRatioBasedSampler(0.1);
const provider = new NodeTracerProvider({ sampler });
```

For error traces, sample 100%:
```ts
const sampler = new ParentBasedSampler({
  root: new ErrorBasedSampler(),  // 100% for errors
  // Otherwise: 10%
});
```

Sampling reduces the data volume while keeping important
traces.

## The "trace backend" choice

| Backend | Self-hosted | Cloud | Notes |
|---|---|---|---|
| **Honeycomb** | ❌ | ✅ | Modern, fast |
| **Datadog** | ❌ | ✅ | Full APM |
| **New Relic** | ❌ | ✅ | Full APM |
| **Jaeger** | ✅ | ❌ | CNCF, mature |
| **Zipkin** | ✅ | ❌ | Twitter, mature |
| **Tempo** | ✅ | ❌ | Grafana ecosystem |

For most apps, **Datadog** or **Honeycomb** is the right
choice.

## The "OpenTelemetry exporters" pattern

```ts
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';

const exporter = new OTLPTraceExporter({
  url: 'https://api.honeycomb.io/v1/traces',
  headers: { 'X-Honeycomb-Team': env.HONEYCOMB_API_KEY },
});

const provider = new NodeTracerProvider({ resource, spanProcessors: [new BatchSpanProcessor(exporter)] });
```

The exporter sends traces to the backend.

## The "auto-instrumentation" pattern

For libraries (express, pg, etc.), use auto-instrumentation:
```ts
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';

const sdk = new NodeSDK({
  instrumentations: [getNodeAutoInstrumentations()],
  traceExporter,
});

sdk.start();
```

The SDK auto-instruments DB calls, HTTP calls, etc.

## The "tracing in production" anti-patterns

### 1. Trace everything
- **Issue:** Every span is sent; the cost is huge
- **Fix:** Sample (1-10% of normal, 100% of errors)

### 2. Trace with PII
- **Issue:** A trace contains user emails, IDs
- **Fix:** Hash PII; don't include in attributes

### 3. Trace without sampling
- **Issue:** Production traffic overwhelms the backend
- **Fix:** Always sample

### 4. Trace without context
- **Issue:** A span has no user.id, tenant.id
- **Fix:** Always set context attributes

## The "tracing + logging correlation" pattern

For correlation, include the trace ID in logs:
```ts
const span = trace.getActiveSpan();
const traceId = span?.spanContext().traceId;

logEvent('user.action', 'info', {
  traceId,
  userId: ctx.user.id,
  action: 'login',
});
```

The trace ID is in the log; you can find the trace from the
log.

## The "tracing for debugging" pattern

For debugging a specific request, find the trace by:
- **Trace ID:** From the response header or log
- **User ID:** From the user's session
- **Time range:** From when the issue happened

In the trace backend:
```ts
// Honeycomb
https://ui.honeycomb.io/my-team/environments/prod/trace/abc123

// Datadog
https://app.datadoghq.com/apm/trace/abc123
```

## Verification
- **Test:** Traces are emitted on every request
- **Live:** Traces are searchable in the backend
- **Audit:** Quarterly review of sampling + retention

## Gotchas
- **The "trace without context" anti-pattern.** A trace
  without user.id, tenant.id is useless for debugging.
- **The "trace with PII" anti-pattern.** Hash PII before
  including in attributes.
- **The "trace without sampling" anti-pattern.** The
  backend is overwhelmed; traces are dropped.
- **The "trace without a backend" anti-pattern.** Traces
  that go nowhere are wasted overhead.
- **The "trace for normal traffic" anti-pattern.** Sample
  1-10%; trace 100% of errors.

## Related
- `observability-three-pillars-detail.md`
- `observability-metrics-design-detail.md`
- `structured-logging.md`
- `error-handling-strategies.md`
- OpenTelemetry: https://opentelemetry.io/
- Honeycomb: https://www.honeycomb.io/
- Datadog: https://www.datadoghq.com/
