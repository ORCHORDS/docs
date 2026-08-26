# OpenTelemetry SDK Instrumentation — Auto vs Manual, Spans, Context Propagation, and Exporters

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team enabled OpenTelemetry auto-instrumentation and gets traces
for HTTP requests and database queries, but you cannot see business
logic spans — order processing, payment validation, or inventory
checks appear as gaps in the trace timeline. A developer adds manual
spans but child spans appear as orphaned root traces because context
propagation broke across an async boundary. Meanwhile, your tracing
backend ingests 50 GB/day because sampling is set to `always_on`.

## Context

OpenTelemetry SDK instrumentation has two modes: auto-instrumentation
(monkey-patching common libraries for HTTP, database, and RPC calls
with zero code changes) and manual instrumentation (explicit span
creation for business logic). The recommended 2026 approach is hybrid
— auto-instrumentation handles infrastructure telemetry while manual
instrumentation adds domain context. Context propagation uses W3C
TraceContext by default, carrying trace-id and parent-id across
service boundaries via the `traceparent` header. SDK configuration
is largely environment-variable-driven, with support for multiple
exporters (OTLP, Jaeger, Prometheus, console) and sampling strategies
(TraceIdRatio, ParentBased, always_on/off).

## Auto-instrumentation vs manual

```
                    Auto                    Manual
──────────────────────────────────────────────────────────────
Setup:              Library/agent install   Code changes required
Coverage:           HTTP, DB, RPC, gRPC     Business logic, domain
Overhead:           Low, fixed              Developer-controlled
Customization:      Limited                 Full control
Recommended for:    Infrastructure spans    Domain spans

Recommended: hybrid — auto for infrastructure, manual for business
logic. Target 5-15 custom spans per request for complex services.
```

## Manual span creation

```typescript
import {
  trace, SpanStatusCode, context
} from '@opentelemetry/api';

const tracer = trace.getTracer('order-service', '2.1.0');

// Active span pattern — auto-propagates context to children
tracer.startActiveSpan('process-order', async (span) => {
  try {
    const order = await fetchOrder(orderId);
    span.setAttributes({
      'order.total': order.total,
      'order.item_count': order.items.length,
    });
    span.setStatus({ code: SpanStatusCode.OK });
    return order;
  } catch (error) {
    span.recordException(error);
    span.setStatus({
      code: SpanStatusCode.ERROR,
      message: error.message,
    });
    throw error;
  } finally {
    span.end();
  }
});

// Events — timestamped moments within a span (cheaper than child spans)
span.addEvent('validation.failed', {
  'validation.error_code': result.errorCode,
});
```

## Context propagation

```
Default propagator: W3C TraceContext

  traceparent: 00-<trace-id>-<parent-id>-<trace-flags>
  Example: 00-0af7651916cd43dd-b7ad6b7169203331-01

  Configured via OTEL_PROPAGATORS environment variable:
    tracecontext,baggage  (default)
    b3,b3multi            (Zipkin compatibility)
    jaeger                (Jaeger native)
    xray                  (AWS X-Ray)
    none                  (disabled)
```

```typescript
// Preserve context across async boundaries
const ctx = context.active();
setTimeout(() => {
  context.with(ctx, () => {
    // child span now correctly parented
    tracer.startActiveSpan('delayed-task', (span) => {
      // ...
      span.end();
    });
  });
}, 100);
```

## SDK configuration (environment variables)

```bash
# Service identity
export OTEL_SERVICE_NAME="order-service"
export OTEL_RESOURCE_ATTRIBUTES="environment=prod,region=us-east"

# Exporters
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_METRICS_EXPORTER="otlp"
export OTEL_LOGS_EXPORTER="otlp"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4317"

# Sampling
export OTEL_TRACES_SAMPLER="parentbased_traceidratio"
export OTEL_TRACES_SAMPLER_ARG="0.05"
```

```
Available samplers:

  Sampler                        Behavior
  ──────────────────────────────────────────────────────────
  always_on                      100% sampling
  always_off                     No sampling
  traceidratio                   Percentage-based on trace ID
  parentbased_always_on          Respect parent, sample roots
  parentbased_traceidratio       Respect parent, ratio for roots
  jaeger_remote                  Dynamic rates from backend

  Production recommendation:
    parentbased_traceidratio at 5-10% for baseline,
    combined with tail sampling at the Collector for
    100% capture of errors and slow traces.
```

## Anti-patterns

- **Forgetting `span.end()`** — causes memory leaks. Always call
  in a `finally` block, never conditionally.
- **Span explosion** — creating a separate span per loop iteration
  or list item instead of one span with events. Events are cheaper
  than child spans for recording individual steps.
- **High-cardinality attributes** — putting raw user IDs, emails,
  or request bodies as attribute values. Use low-cardinality
  values like `email_domain` or `user_tier` to avoid index
  explosion in the tracing backend.
- **Not setting span status on error** — spans without
  `SpanStatusCode.ERROR` and `recordException()` will not surface
  in error-rate dashboards or alerting rules.

## Gotchas

- **Lost context in callbacks and timers** — child spans silently
  become orphaned root traces if `context.active()` is not captured
  before the async boundary and restored with `context.with()`.
- **Auto-instrumentation does not cover custom business logic** —
  it only wraps known library calls. Domain-specific operations
  (order validation, inventory checks) require manual spans.
- **`always_on` sampling in production** — generates massive data
  volumes. A 1000 RPS service with 10 spans per request at
  `always_on` produces 36 million spans per hour.
- **Resource attributes vs span attributes** — resource attributes
  (service name, environment, region) are set once per SDK instance
  and apply to all spans. Span attributes are per-span. Putting
  per-request data in resource attributes wastes memory.

## Verification

- Hybrid instrumentation configured: auto for libraries, manual for business logic.
- `span.end()` called in `finally` blocks for all manual spans.
- Context propagation preserved across async boundaries.
- Sampling configured with `parentbased_traceidratio` in production.
- Resource attributes include service name, environment, and region.
- Span attributes use low-cardinality values only.

## Related

- `documentation/categories/monitoring/opentelemetry-collector-pipeline.md`
- `documentation/categories/monitoring/distributed-tracing-correlation.md`
- `documentation/categories/devtools/ai-assisted-code-review-tools.md`

## Source URLs (verified 2026-08-16)

- Manual vs Auto Instrumentation: Choose What's Right — https://cribl.io/blog/manual-vs-auto-instrumentation-opentelemetry-choose-whats-right/
- General SDK Configuration (OpenTelemetry) — https://opentelemetry.io/docs/languages/sdk-configuration/general/
- How to Implement OpenTelemetry Manual Instrumentation — https://oneuptime.com/blog/post/2026-01-30-opentelemetry-manual-instrumentation/view
- OpenTelemetry Context Propagation — https://oneuptime.com/blog/post/2026-02-02-opentelemetry-context-propagation/view
