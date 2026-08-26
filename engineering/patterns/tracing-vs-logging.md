# tracing-vs-logging

**Issue:** When to use tracing vs structured logging
**Date:** 2026-08-09
**Status:** documented

## Symptom
You add a trace to every request. The trace is great. You also
add a log line for every span. Now you have 2x the data. The
storage cost is high. The on-call is confused about which to
look at first.

## Root cause
**Tracing and logging are complementary, not redundant.** Each
serves a different purpose. Using both correctly is an art.

**Source:** OpenTelemetry — Logs and Traces:
https://opentelemetry.io/docs/concepts/signals/

## The mental model

### Logs: events
- "What happened at this moment"
- A discrete fact, with context
- Examples: "user signed up", "payment failed", "rate limit hit"

### Traces: flows
- "How did this request flow through the system"
- A series of connected operations
- Examples: "the request went through auth → db → cache → response"

### Metrics: aggregates
- "How often, how fast, how big"
- A number, with dimensions
- Examples: "request count by endpoint", "p99 latency by service"

## When to use which

### Use logs when:
- **You need to debug a specific event** ("why did this user
  see an error at 3pm?")
- **The event is a milestone** (signup, purchase, etc.)
- **You need to know what data was involved** (request body,
  user ID, etc.)
- **The volume is low** (< 1000 events/sec)

### Use traces when:
- **You need to debug a slow request** ("why is this endpoint
  slow for some users?")
- **The request spans multiple services** (Pages Function + DO
  + vendor API)
- **You need to find the bottleneck** (which service is the
  slowest?)
- **You need to understand the dependency graph** (which
  service depends on which?)

### Use metrics when:
- **You need to track an SLO** (p99 latency, error rate)
- **You need an alert** (alert when error rate > 5%)
- **You need a dashboard** (overview of the system)
- **The data is high-cardinality** (per-tenant, per-endpoint)

## The anti-patterns

### Tracing every log line
A trace span is overhead (~10-50ms). Don't wrap every log line
in a span.

### Logging every span
A log line is overhead (storage + query cost). Don't log
inside every span.

### Treating them as the same
If you're using tracing AND logging, decide which is the
"source of truth" for each piece of information.

## The pragmatic approach

For most apps:
1. **Logs:** Use structured logging (JSON) for all events
2. **Traces:** Use sampling (1-10%) for request flows
3. **Metrics:** Aggregate from logs or use a separate system
4. **Errors:** Logged with full context; correlated with trace
   ID

```ts
// 1. Structured log
console.log({
  level: 'error',
  message: 'payment.failed',
  userId: 'u_123',
  amount: 100,
  currency: 'USD',
  error: err.message,
  traceId: 'abc-123',  // <-- link to the trace
});

// 2. Trace span (sampled)
return tracer.startActiveSpan('handlePayment', async (span) => {
  span.setAttribute('user.id', userId);
  span.setAttribute('payment.amount', 100);
  try {
    const result = await processPayment();
    span.setStatus({ code: SpanStatusCode.OK });
    return result;
  } catch (err) {
    span.setStatus({ code: SpanStatusCode.ERROR, message: err.message });
    span.recordException(err);
    throw err;
  } finally {
    span.end();
  }
});

// 3. Metric
env.ANALYTICS.writeDataPoint({
  blobs: ['payment', 'failed', err.code],
  doubles: [100, durationMs],
  indexes: ['payment'],
});
```

## The decision tree

```
Question: What do you need to know?

  "What happened"                  → Log
    ├─ Low volume, specific event  → ✓ use this
    └─ High volume, general event  → Metric

  "Why is it slow / failing"      → Trace
    ├─ Single service              → Log + metric (trace optional)
    └─ Multiple services           → ✓ use this

  "How many / how often"           → Metric
    ├─ SLO tracking                → ✓ use this
    └─ Alerting                    → ✓ use this

  "How to debug a specific event"  → Log (with traceId)
  "How to debug a slow request"    → Trace
  "How to track the overall health" → Metric
```

## Verification
- **Test:** `test/telemetry.test.ts > request emits 1 trace,
  1 metric, N logs` — passes
- **Live:** The on-call can find the answer in < 5 minutes
  (debugging by trace)
- **Audit:** Quarterly review of log/trace/metric coverage

## Gotchas
- **The cost adds up.** 1000 RPS × 10 log lines × 1KB = 10MB/s
  = 850GB/day. Sample logs (1-10%) for high-volume paths.
- **PII in logs is a compliance issue.** Hash user IDs; don't
  log request bodies.
- **The trace ID is the correlation key.** Include it in every
  log line, so you can find the trace from the log and vice
  versa.
- **Some libraries log AND trace.** You get duplicate data.
  Configure the library to do one (usually trace is cheaper).
- **The "right" answer depends on the team's tooling.**
  Datadog-centric teams use Datadog's APM. Honeycomb-centric
  teams use traces + logs. Choose what your team knows.

## Related
- `observability-three-pillars.md`
- `tracing-distributed.md`
- `error-budget-slo.md` (uses metrics)
- OpenTelemetry: https://opentelemetry.io/
- Honeycomb: https://www.honeycomb.io/
