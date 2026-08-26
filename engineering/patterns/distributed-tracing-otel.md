# distributed-tracing-otel

**Issue:** Distributed tracing — OpenTelemetry + W3C context
**Date:** 2026-08-09
**Status:** documented

## Symptom
A request goes through 5 services. Latency is 3 sec.
Which service is slow? You have no idea. Logs are
unrelated. Metrics are aggregated. You wish you had
distributed tracing.

## Root cause
**Without context, distributed systems are black
boxes.** Use OpenTelemetry.

**Source:** OpenTelemetry docs:
https://opentelemetry.io/docs/concepts/context-propagation/

## The "distributed tracing" concept

Distributed tracing:
- **Trace:** Full request flow across services
- **Span:** Single operation in a trace
- **Trace ID:** Unique per request
- **Span ID:** Unique per operation
- **Context:** Carried across boundaries

The trace is the request story.

## The "W3C Trace Context" standard

For propagation:
- **Header:** `traceparent: version-traceid-spanid-flags`
- **Example:** `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- **Plus:** `tracestate` (vendor-specific)

The standard is W3C.

## The "context propagation" pattern

For propagation:
- **Inject:** Sender adds context to carrier
- **Extract:** Receiver pulls from carrier
- **Carriers:** HTTP headers, gRPC metadata, message
  headers
- **Auto:** Most libs handle

The context flows.

## The "OpenTelemetry SDK" pattern

For setup:
```typescript
import { trace, SpanStatusCode } from "@opentelemetry/api";
import { NodeSDK } from "@opentelemetry/sdk-node";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";

const sdk = new NodeSDK({
  serviceName: "my-service",
  instrumentations: [getNodeAutoInstrumentations()],
});

sdk.start();
```

The SDK auto-instruments.

## The "auto-instrumentation" pattern

For auto:
- **HTTP (HTTPx, fetch):** Server + client
- **gRPC:** Server + client
- **Database:** Per driver
- **Queue:** Producer + consumer
- **Framework:** Express, FastAPI, etc.

The auto covers most.

## The "manual instrumentation" pattern

For manual:
```typescript
import { trace } from "@opentelemetry/api";

const tracer = trace.getTracer("my-service");

const span = tracer.startSpan("process_order", {
  kind: SpanKind.INTERNAL,
  attributes: {
    "order.id": orderId,
    "order.amount": amount,
  },
});

try {
  // business logic
  span.setStatus({ code: SpanStatusCode.OK });
} catch (e) {
  span.recordException(e);
  span.setStatus({ code: SpanStatusCode.ERROR, message: e.message });
  throw e;
} finally {
  span.end();
}
```

The manual is for custom.

## The "span kinds" pattern

For span kind:
- **SERVER:** Incoming request
- **CLIENT:** Outgoing request
- **PRODUCER:** Message published
- **CONSUMER:** Message received
- **INTERNAL:** Internal operation

The kind is per role.

## The "semantic conventions" pattern

For attributes:
- **HTTP:** `http.method`, `http.status_code`, `http.url`
- **DB:** `db.system`, `db.statement`, `db.name`
- **RPC:** `rpc.system`, `rpc.service`, `rpc.method`
- **Messaging:** `messaging.system`, `messaging.destination`

The conventions are OTel-defined.

## The "context across async" pattern

For async:
```python
# Producer
from opentelemetry import trace
from opentelemetry.propagate import inject

ctx = trace.get_current_span().get_span_context()
headers = {}
inject(headers)  # Injects traceparent

queue.send({"headers": headers, "body": data})

# Consumer
from opentelemetry.propagate import extract
ctx = extract(message["headers"])

with tracer.start_as_current_span("process_message", context=ctx):
    process(message["body"])
```

The context flows through queue.

## The "service.name" pattern

For resource attribute:
```typescript
resource: Resource.default().merge(
  new Resource({
    "service.name": "my-service",
    "service.version": "1.2.3",
    "deployment.environment": "production",
  })
)
```

The name is required.

## The "business context" pattern

For business attrs:
```typescript
span.setAttribute("order.id", order.id);
span.setAttribute("order.amount", order.amount);
span.setAttribute("user.id", user.id);
span.setAttribute("user.tier", "premium");
```

The context is meaningful.

## The "baggage" pattern

For cross-cutting data:
```typescript
import { propagation, context } from "@opentelemetry/api";

// Set
const ctx = propagation.setBaggage(context.active(), {
  userId: { value: "123" },
  tenantId: { value: "acme" },
});

// Get (in downstream)
const baggage = propagation.getBaggage(ctx);
const userId = baggage?.userId?.value;
```

The baggage flows.

**Caveat:** Don't put PII or secrets in baggage.

## The "error recording" pattern

For errors:
```typescript
try {
  await doWork();
} catch (e) {
  span.recordException(e);
  span.setStatus({
    code: SpanStatusCode.ERROR,
    message: e.message,
  });
  throw e;
}
```

The error is recorded.

## The "trace sampling" pattern

For sampling:
- **Always On:** All traces
- **Always Off:** No traces
- **ParentBased:** Inherit parent
- **TraceIDRatio:** % of traces
- **RateLimiting:** N per second

The sampling is per service.

## The "tail-based sampling" pattern

For late decisions:
- **Capture all spans:** At edge
- **Decide late:** At collector
- **Keep:** Errors, slow, sampled %
- **Drop:** Fast + sampled

The tail is at collector.

## The "OTLP exporter" pattern

For export:
```typescript
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";

const exporter = new OTLPTraceExporter({
  url: "https://otel-collector:4318/v1/traces",
});
```

The exporter is OTLP.

## The "collector deployment" pattern

For collector:
- **Agent:** Per host (DaemonSet)
- **Gateway:** Centralized
- **Receivers:** OTLP, Jaeger, Zipkin
- **Processors:** Batch, tail-sample
- **Exporters:** Jaeger, Tempo, Honeycomb

The collector is the pipeline.

## The "tracing backend" pattern

For backends:
- **Jaeger:** OSS, popular
- **Tempo:** Grafana
- **Zipkin:** Old, OSS
- **Honeycomb:** SaaS
- **Datadog APM:** SaaS
- **New Relic:** SaaS
- **SigNoz:** OSS alternative

The backend is per choice.

## The "untrusted context" pattern

For security:
- **Issue:** External services can inject
  malicious trace headers
- **Fix:** Sanitize or ignore from untrusted
- **Outgoing:** Don't send to public endpoints

The context is sanitized.

## The "no auto-instrumentation" anti-pattern

For no auto:
- **Issue:** Manual everywhere
- **Fix:** Use auto-instrumentation libs

The auto is the default.

## The "no service.name" anti-pattern

For no service name:
- **Issue:** Can't filter in UI
- **Fix:** Set service.name + version + env

The name is set.

## The "no business context" anti-pattern

For no business ctx:
- **Issue:** Only technical spans
- **Fix:** Add order.id, user.id, etc.

The context is business.

## The "no error recording" anti-pattern

For no error:
- **Issue:** Span shows OK, error in log
- **Fix:** recordException + setStatus

The error is recorded.

## The "traceparent not propagated" anti-pattern

For no propagation:
- **Issue:** Disconnected spans
- **Fix:** Use auto-instrumentation or manual
  extract/inject

The propagation is on.

## The "PII in baggage" anti-pattern

For PII in baggage:
- **Issue:** GDPR + propagation leak
- **Fix:** No PII in baggage

The baggage is sanitized.

## The "tracing checklist" pattern

For checklist:
- [ ] Service.name set
- [ ] Auto-instrumentation on
- [ ] Manual for custom spans
- [ ] Error recorded + status set
- [ ] Business context added
- [ ] Context propagated (HTTP, gRPC, queue)
- [ ] Sampling configured
- [ ] OTLP exporter to collector
- [ ] Backend deployed
- [ ] No PII in baggage

The checklist is comprehensive.

## Verification
- **Test:** Trace flows across services
- **Test:** Trace ID in logs
- **Test:** Errors show in trace
- **Test:** Span duration accurate
- **Audit:** Quarterly

## Gotchas
- **The "no propagation" anti-pattern.** Inject + extract.
- **The "no service.name" anti-pattern.** Set it.
- **The "PII in baggage" anti-pattern.** Sanitize.

## Related
- `patterns/observability-three-pillars.md`
- `patterns/structured-logging-detail.md`
- `patterns/slo-error-budget-deep-dive.md`
- `patterns/incident-response.md`
- OneUptime: https://oneuptime.com/blog/post/2026-01-24-distributed-tracing-across-services/view
- Red Hat: https://developers.redhat.com/articles/2026/04/06/distributed-tracing-agentic-workflows-opentelemetry
- OTel: https://opentelemetry.io/docs/concepts/context-propagation/
