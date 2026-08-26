# OpenTelemetry for Local Dev (Distributed Tracing in Development)

> Adding OpenTelemetry (OTel) traces, metrics, and logs to a multi-service dev
> environment so you can see cross-service request flow locally — without
> standing up a full observability stack or shipping data to a vendor.

---

## When to use this

- A request flows through 2+ services (e.g. web → API → worker → DB) and the
  bug is "somewhere in between".
- Latency is intermittent and only reproducible locally.
- You're about to add `console.log` to ten files just to trace one request.
- You want production-style observability in dev without a Datadog bill.

## Symptom

"Request X is slow / failing, and I have no idea which service is responsible."

Manual `console.log` proliferation across services:
- pollutes the codebase
- is hard to correlate (whose log line was first?)
- doesn't capture the actual span durations
- gets removed before commit, then the bug comes back

## Minimal local stack

The smallest useful setup is **OTel SDK in your app + a local collector + a
UI**. Jaeger is the lightest UI; Tempo+Grafana is the most common upgrade path.

### 1. Run the collector + UI with Docker

```yaml
# docker-compose.otel.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.62
    ports: ["16686:16686", "4318:4318"]   # UI, OTLP/HTTP
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
```

```bash
docker compose -f docker-compose.otel.yml up -d
# UI at http://localhost:16686
# Apps export to http://localhost:4318/v1/traces
```

That's the whole backend. No storage config needed — all-in-one keeps spans
in memory, which is fine for dev sessions.

### 2. Instrument a Node app

```bash
npm install @opentelemetry/sdk-node \
  @opentelemetry/auto-instrumentations-node \
  @opentelemetry/exporter-trace-otlp-http
```

```js
// tracing.js — MUST be required before your app code
const { NodeSDK } = require('@opentelemetry/sdk-node');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter({
    url: 'http://localhost:4318/v1/traces',
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});
sdk.start();
```

Run with `node -r ./tracing.js app.js`. The auto-instrumentation gives you
spans for HTTP in/out, Express routes, DB queries (pg, mysql, mongodb, redis),
and `fetch` — with no code changes.

### 3. Propagate across services

The magic is **context propagation**. For a request flowing web → api:

- Auto-instrumented HTTP client (axios/fetch) injects `traceparent` /
  `tracestate` headers automatically.
- Auto-instrumented HTTP server on the receiving side extracts them.
- Result: one tree in Jaeger spanning both services.

This works automatically **if both services use the OTel SDK and the default
W3C TraceContext propagator**. If you see two disconnected traces, propagation
is broken — usually because one side isn't instrumented yet or a manual
`fetch` call stripped the headers.

### 4. Add custom spans where it matters

```js
const { trace } = require('@opentelemetry/api');
const tracer = trace.getTracer('my-app');

async function chargeCard(userId, amount) {
  return tracer.startActiveSpan('chargeCard', async (span) => {
    span.setAttribute('user.id', userId);
    span.setAttribute('payment.amount', amount);
    try {
      const result = await stripe.charges.create(/* ... */);
      span.setAttribute('payment.charge_id', result.id);
      return result;
    } catch (err) {
      span.recordException(err);
      span.setStatus({ code: 2, message: err.message });
      throw err;
    } finally {
      span.end();
    }
  });
}
```

Keep custom spans for **business-meaningful operations** — don't wrap every
function. Auto-instrumentation already covers I/O.

## Gotchas

- **`tracing.js` must load first**: if your app code imports before OTel
  patches the modules, you get zero spans. Use `-r ./tracing.js` (Node) or
  load via `--javaagent` (JVM) or `opentelemetry-instrument` (Python).
- **Span explosion = UI lag**: `getNodeAutoInstrumentations()` enables every
  instrumented library including `dns` and `net`. In dev this is fine; in a
  load test it will overwhelm Jaeger's in-memory store. Filter with
  `@opentelemetry/instrumentation-http` `ignoreIncomingRequestHook`.
- **Sampling defaults hide the bug**: the default `ParentBased(AlwaysOn)`
  sampler keeps 100% but a remote parent with sampled=false propagates as
  not-sampled. Set `OTEL_TRACES_SAMPLER=always_on` for local dev to avoid
  "I reproduced it but the trace is gone".
- **Async hooks + Jest = flakiness**: OTel relies on `AsyncLocalStorage`. In
  Jest workers with parallel test isolation this sometimes loses context. For
  unit tests, disable auto-instrumentation; only assert on spans in
  integration tests.
- **gRPC vs HTTP export**: 4317 is gRPC, 4318 is HTTP. Mixing them up produces
  silent no-ops. Auto-instrumentation defaults to gRPC; the HTTP exporter
  needs the explicit `url` shown above.
- **DB spans show the query, not the bind values**: OTel redacts DB statement
  parameters by default (good for prod, annoying for dev). Set
  `OTEL_INSTRUMENTATION_PG_CAPTURE_STATEMENT_CONCAT=true` (pg-specific) to see
  the full query during local debugging.
- **One trace per request, not per log line**: novices wrap each log call in
  a span, producing thousands of spans. Logs should be **log records
  associated with a span** (via `trace.getActiveSpan().recordException` or
  OTel logs API), not separate spans.
- **Clock skew between containers**: spans are timestamped at the source. If
  the web container clock is 2s ahead of the DB container (common on Docker
  Desktop for Windows), Jaeger shows impossible ordering. Sync with
  `docker run --cap-add SYS_TIME ...` or use NTP in long-lived containers.
- **Trace context lost across a queue**: Redis / SQS / RabbitMQ breaks the
  in-process context. You must manually inject the context into the message
  payload on the producer side and extract it in the consumer. Auto-
  instrumentation does NOT do this for you in most messaging libs.

## Quick triage checklist

- [ ] Both services export to `localhost:4318` and the collector is up?
- [ ] Both services load the SDK before app code?
- [ ] Sampler is `always_on` (dev) so you actually see the trace?
- [ ] One trace ID appears in both services, or two separate traces?
- [ ] Spans for the suspect operation end when you expect, not earlier?

## See also

- `docker-compose-dev.md` — running the multi-service stack
- `bottom-system-monitor.md` — process-level metrics (complementary)
- `hyperfine-benchmarking.md` — single-function perf (finer-grained)
