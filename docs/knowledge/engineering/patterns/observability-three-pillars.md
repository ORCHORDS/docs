# observability-three-pillars

**Issue:** Logs + metrics + traces — when to use which
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your service is broken. You grep logs for the error. You find
a stack trace. The stack trace says "Database timeout." You
have no idea which request triggered it, which user, or what
the database was doing.

## Root cause
**Logs are necessary but not sufficient.** Logs answer "what
happened." Metrics answer "how often + how fast." Traces
answer "where in the request flow did it happen."

**Source:** Honeycomb — The Three Pillars of Observability:
https://www.honeycomb.io/blog/observability-101-the-three-pillars

> "Logs, metrics, and traces are three different ways to
> describe a system. Each is useful for different questions."

## The three pillars

### 1. Logs (events)
- **What:** Discrete events with structured data
- **When:** Detailed debugging, post-mortem analysis
- **Format:** `JSON.stringify({ timestamp, level, message, ...context })`
- **Tool:** CF Workers Tail, Logpush, Sentry, Datadog
- **Example:** `{ level: "error", message: "DB timeout", user_id: "u_123", request_id: "req_456" }`

### 2. Metrics (numbers)
- **What:** Aggregated counters + gauges + histograms
- **When:** Dashboards, alerting, SLO tracking
- **Format:** Numeric, with tags
- **Tool:** CF Analytics Engine, Prometheus, Datadog
- **Example:** `counter("requests_total")` `{ endpoint: "/api/users", status: 500 }`

### 3. Traces (request flow)
- **What:** A request's path through multiple services
- **When:** Performance debugging, distributed system analysis
- **Format:** Span tree (parent → children)
- **Tool:** OpenTelemetry, Honeycomb, Jaeger
- **Example:** `trace.span("/api/users", parent: "req_456", duration_ms: 320) { child: "db.query", child: "cache.get" }`

## When to use which

| Question | Use |
|---|---|
| "What error did user 123 see at 3pm?" | Logs |
| "What's our p99 latency for /api/users?" | Metrics |
| "Why was that specific request slow?" | Traces |
| "Is the error rate increasing?" | Metrics |
| "What was the user doing when it failed?" | Logs |
| "Which downstream service is the bottleneck?" | Traces |

## The CF Workers context

CF Workers + Pages has specific observability primitives:

### `console.log` (free, dev-friendly)
```ts
console.log('User created', { userId, tenantId });
// Visible in `wrangler tail` and CF dashboard
```

### `env.ANALYTICS.writeDataPoint()` (aggregated metrics)
```ts
env.ANALYTICS.writeDataPoint({
  blobs: [endpoint, status, errorKind],
  doubles: [durationMs],
  indexes: [endpoint],
});
// Visible in CF Analytics Engine query
```

### `tracer` (OpenTelemetry)
```ts
import { tracer } from './tracer';
return tracer.startActiveSpan('handleRequest', async (span) => {
  span.setAttribute('user_id', userId);
  try {
    const result = await handler();
    span.setStatus({ code: SpanStatusCode.OK });
    return result;
  } catch (err) {
    span.setStatus({ code: SpanStatusCode.ERROR, message: err.message });
    throw err;
  } finally {
    span.end();
  }
});
```

## Logpush (for long-term log retention)

`console.log` only retains logs for 3 days (free) or 30 days
(paid). For longer retention:
```toml
# wrangler.toml
[[logpush]]
destination = "r2"
dataset = "production_logs"
```

This pushes all logs to R2 (or a third-party like Datadog).

## Structured logging

Always use structured logs. Free-form strings are hard to query.

```ts
// ❌ Bad: free-form
console.log(`User ${userId} created post ${postId} but it failed`);

// ✅ Good: structured
console.log({
  level: 'error',
  message: 'post.create.failed',
  userId,
  postId,
  error: err.message,
  durationMs: 1234,
});
```

In your log aggregator, query for `message = "post.create.failed"`.

## Verification
- **Test:** Each request emits exactly 1 trace span + N logs
  + M metrics
- **Live:** Dashboard shows p50/p95/p99 latency, error rate,
  and request count for the main endpoints
- **Audit:** Quarterly review of dashboard + alerting rules

## Gotchas
- **Logs are expensive at scale.** A 1000-RPS service emits
  86M log lines/day. Sample aggressively (1-10%) for
  high-traffic paths.
- **Metrics are aggregated — you lose individual events.** For
  debugging a specific user, you need logs.
- **Traces need request IDs.** Every log line, every metric
  should include the `request_id` so you can correlate.
- **CF Workers console.log has a 1KB limit per line.** For long
  output, split or truncate.
- **OpenTelemetry adds overhead.** For chatty paths, the span
  cost is non-trivial. Profile before instrumenting everything.

## Related
- `error-budget-slo.md` (uses metrics for SLO tracking)
- `audit-log-mandatory.md` (uses logs for compliance)
- Honeycomb: https://www.honeycomb.io/blog/observability-101-the-three-pillars
- CF Analytics: https://developers.cloudflare.com/analytics/
- OpenTelemetry: https://opentelemetry.io/
