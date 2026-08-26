# tracing-distributed

**Issue:** Trace a request across multiple Workers + DOs
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user reports "the page is slow." You look at the main
endpoint's logs: 800ms. The D1 query is fast. The R2 fetch
is fast. But the page is slow. Where's the time going?

## Root cause
**Logs from a single function don't tell the full story.** A
request might span:
- The main Pages Function
- A Durable Object
- D1 (multiple queries)
- R2 (fetch)
- A vendor API (fetch)

Each of these is its own log line. To understand the total
latency, you need a **trace** that connects them.

**Source:** OpenTelemetry distributed tracing:
https://opentelemetry.io/docs/concepts/signals/traces/

> "Distributed tracing ... provides a way to track a request
> as it moves through different services."

## The trace model

A trace is a tree of spans:
```
trace: req_abc
├── span: handler (800ms)
│   ├── span: auth (50ms)
│   ├── span: db.users.find (100ms)
│   ├── span: db.posts.list (200ms)
│   ├── span: do.session.get (50ms)
│   └── span: r2.image.fetch (400ms)
```

The parent is the entry point. Children are the operations
within. Each span has a start time, duration, and attributes.

## Implementation with OpenTelemetry

```ts
import { trace, SpanStatusCode } from '@opentelemetry/api';

const tracer = trace.getTracer('example project-api');

export const onRequest: PagesFunction<Env> = async (context) => {
  return tracer.startActiveSpan('handler', async (span) => {
    const { request, env } = context;
    const url = new URL(request.url);
    span.setAttribute('http.url', url.toString());
    span.setAttribute('http.method', request.method);

    try {
      // Auth
      await tracer.startActiveSpan('auth', async (authSpan) => {
        const ctx = await authenticate(request, env);
        if (!ctx) {
          authSpan.setStatus({ code: SpanStatusCode.ERROR, message: 'unauthorized' });
          return new Response('Unauthorized', { status: 401 });
        }
        span.setAttribute('user.id', ctx.user.id);
        authSpan.end();
      });

      // DB query
      const posts = await tracer.startActiveSpan('db.posts.list', async (dbSpan) => {
        const result = await env.DB!.prepare(
          `SELECT * FROM posts WHERE user_id = ? LIMIT 20`
        ).bind(ctx.user.id).all();
        dbSpan.setAttribute('db.rows', result.results.length);
        dbSpan.end();
        return result;
      });

      span.setStatus({ code: SpanStatusCode.OK });
      return new Response(JSON.stringify({ posts: posts.results }), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    } catch (err) {
      span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
      throw err;
    } finally {
      span.end();
    }
  });
};
```

## Propagation across Durable Objects

For a DO call, the trace context must be propagated:
```ts
// Caller
const traceparent = `00-${spanId}-${traceId}-01`;  // W3C trace context
await stub.fetch('https://do/event', {
  method: 'POST',
  body: JSON.stringify(event),
  headers: { traceparent },
});

// Callee (in the DO)
export class AuditChainDO {
  async fetch(req: Request): Promise<Response> {
    const traceparent = req.headers.get('traceparent');
    // Parse and continue the trace
    return tracer.startActiveSpan('auditChain.write', { links: [/* parsed */] }, async (span) => {
      // ...
      span.end();
    });
  }
}
```

## Sampling

Tracing every request is expensive (10-50ms overhead per span,
KB of data per trace). For high-traffic services, sample:
- **1-10% of requests** is typical
- **Always trace errors** (the rare events you care about)
- **Always trace slow requests** (p95+)
- **Head-based:** decide to trace at the start of a request
- **Tail-based:** decide after the request completes (more
  accurate, more complex)

```ts
const SAMPLE_RATE = 0.1;  // 10% of requests
if (Math.random() > SAMPLE_RATE) {
  // Don't start a span
  return handleRequest(...);
}
```

## Visualization

Send traces to:
- **Honeycomb** — best for high-cardinality data (per-tenant,
  per-user)
- **Datadog APM** — if you already use Datadog
- **Jaeger** — open-source
- **CF Workers Analytics Engine** — built-in, but no full
  distributed tracing

## Verification
- **Test:** `test/tracing.test.ts` — span is created + has
  correct attributes + parent-child relationship
- **Live:** Dashboard shows p50/p95/p99 per span; error traces
  are highlighted
- **Audit:** Annual review of sampling rate + retention

## Gotchas
- **Trace context is sensitive.** If a user ID is in the span,
  PII is in the trace. Use PII redaction (e.g. hash the user
  ID before storing).
- **OpenTelemetry has many SDKs.** Use the official `@opentelemetry/api`
  for compatibility, not a custom protocol.
- **The W3C trace context format is the standard.** Use it
  (`traceparent`, `tracestate` headers) for cross-service
  compatibility.
- **Spans have limits.** Don't put huge data in span
  attributes (10KB per span is the soft limit). Reference
  by ID and link to the actual data.
- **Distributed tracing doesn't replace logs.** Use both:
  tracing for the structure, logs for the detail.

## Related
- `observability-three-pillars.md`
- `error-budget-slo.md` (uses traces to debug SLO breaches)
- `per-tenant-durable-object.md` (DO tracing)
- OpenTelemetry: https://opentelemetry.io/
- W3C trace context: https://www.w3.org/TR/trace-context/
