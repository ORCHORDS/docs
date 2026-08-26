# observability-three-pillars-detail

**Issue:** Metrics, logs, traces — what to capture, when to use which
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app is slow. Users complain. You check the logs: "GET
/api/users 200 in 1.2s." You don't know WHY it's slow. Is
it the DB? The vendor API? The D1? You don't know what
to fix.

## Root cause
**Logs alone are not enough.** You need metrics (numerical
data over time), logs (events), and traces (request flow
across services). Each tells a different story.

**Source:** OpenTelemetry:
https://opentelemetry.io/

> "Observability is the ability to understand the internal
> state of a system by examining its outputs. ... Metrics,
> logs, and traces are the three pillars of observability."

## The 3 pillars

### 1. Metrics
- **What:** Numerical data aggregated over time
- **Examples:** Request count, latency p99, error rate,
  CPU usage, DB query time
- **Storage:** Time-series DB (Prometheus, Datadog,
  CloudWatch)
- **Query:** "What's the p99 latency for the last hour?"
- **When:** Aggregate trends, dashboards, alerts

```ts
// At the end of each request
metrics.histogram('http_request_duration_ms', duration, {
  method: 'GET',
  path: '/api/users',
  status: 200,
});
metrics.increment('http_requests_total', {
  method: 'GET',
  path: '/api/users',
  status: 200,
});
```

### 2. Logs
- **What:** Discrete events with context
- **Examples:** "User u_123 logged in", "Failed to send
  email"
- **Storage:** Log aggregator (Splunk, Datadog, R2)
- **Query:** "Show me all errors for user u_123"
- **When:** Debugging, audits, compliance

```ts
logEvent('user.login.failed', 'warn', {
  userId: 'u_123',
  ip: '192.168.1.1',
  reason: 'wrong_password',
});
```

### 3. Traces
- **What:** The flow of a single request across services
- **Examples:** "GET /api/users" → CF Worker → D1 → vendor
  API → response
- **Storage:** Trace backend (Honeycomb, Jaeger, Datadog)
- **Query:** "Show me the trace for request X"
- **When:** Debugging slow requests, understanding request
  flow

```ts
const tracer = trace.getTracer('my-app');
const span = tracer.startSpan('getUser');
span.setAttribute('user.id', 'u_123');
try {
  const user = await db.query(...);
  span.setAttribute('user.email', user.email);
  return user;
} catch (err) {
  span.recordException(err);
  throw err;
} finally {
  span.end();
}
```

## The "metrics vs logs vs traces" choice

| Question | Use |
|---|---|
| "What's the p99 latency?" | Metrics |
| "Show me errors in the last hour" | Logs |
| "Why is this specific request slow?" | Traces |
| "How many users signed up today?" | Metrics |
| "What did user u_123 do?" | Logs |
| "What services did this request touch?" | Traces |

## The "RED method" for services

For each service, track:
- **Rate:** Requests per second
- **Errors:** Failed requests per second
- **Duration:** Latency distribution (p50, p95, p99)

```ts
// At the end of each request
const duration = Date.now() - start;
metrics.histogram('service_request_duration_seconds', duration / 1000, {
  service: 'user-service',
  endpoint: '/api/users',
  method: 'GET',
  status: 200,
});
metrics.increment('service_requests_total', {
  service: 'user-service',
  endpoint: '/api/users',
  method: 'GET',
  status: 200,
});
```

## The "USE method" for resources

For each resource (CPU, memory, disk, network), track:
- **Utilization:** % of resource used
- **Saturation:** Queue length / wait time
- **Errors:** Error count

```ts
// Worker
metrics.gauge('worker_memory_used_bytes', memoryUsage);
metrics.gauge('worker_cpu_pct', cpuUsage);

// D1
metrics.histogram('d1_query_duration_ms', queryDuration, {
  query: 'select_user',
});
metrics.gauge('d1_storage_used_bytes', storageUsed);

// Vendor API
metrics.histogram('vendor_request_duration_ms', duration, {
  vendor: 'openai',
  endpoint: 'chat',
});
```

## The "SLO" pattern

A Service Level Objective is a target for a metric:
- **99% of requests succeed** (error rate < 1%)
- **99% of requests are < 200ms** (latency p99 < 200ms)
- **99.9% uptime** (downtime < 8.7 hours/year)

```ts
// SLO calculation
const slo = 0.99;  // 99%
const totalRequests = metrics.sum('service_requests_total');
const failedRequests = metrics.sum('service_requests_failed_total');
const actual = 1 - (failedRequests / totalRequests);

if (actual < slo) {
  alert('SLO breach', { actual, slo });
}
```

## The "error budget" pattern

If your SLO is 99%, you have 1% "error budget" — 1% of
requests can fail without violating the SLO. Use the budget:
- ✅ **Spend it** on risky deploys (test in production)
- ❌ **Don't go over** — if you do, freeze deploys and fix
  the bug

```ts
const errorBudgetRemaining = 1 - actualErrorRate;  // 0.01 = 1% budget
if (errorBudgetRemaining < 0) {
  freezeDeploys();
}
```

## The "alerting" pattern

Don't alert on every metric. Alert on:
- **SLO breach** (the SLO is at risk)
- **Error budget exhausted** (no more room to fail)
- **Anomaly** (sudden spike in error rate)
- **Saturation** (DB is at 90% capacity)

```ts
// Alert: error rate > 5% for 5 minutes
if (errorRate > 0.05) {
  pageOncall('High error rate', { rate: errorRate });
}

// Alert: p99 latency > 500ms for 5 minutes
if (p99Latency > 500) {
  pageOncall('High latency', { p99: p99Latency });
}
```

## The "correlation" pattern

Connect metrics, logs, and traces via a request ID:
```ts
const requestId = ctx.requestId;

// In metrics
metrics.histogram('http_request_duration_ms', duration, {
  request_id: requestId,
});

// In logs
logEvent('user.fetched', 'info', { request_id: requestId, userId: 'u_123' });

// In traces
span.setAttribute('request_id', requestId);
```

Now you can:
- See a slow request in metrics → get the request ID
- Find the logs for that request ID
- See the trace for that request ID

The three pillars become one story.

## The "CF Workers + Observability" stack

For CF Workers, the practical stack:
- **Metrics:** Cloudflare Analytics (built-in) +
  Workers Analytics Engine
- **Logs:** Workers Logs (built-in) + Logpush to R2/Datadog
- **Traces:** OpenTelemetry + a trace backend (Honeycomb,
  Datadog, Jaeger)

```ts
// OpenTelemetry in a Worker
import { trace, SpanStatusCode } from '@opentelemetry/api';

const tracer = trace.getTracer('my-worker');

export default {
  async fetch(request, env, ctx) {
    const span = tracer.startSpan('worker.fetch');
    span.setAttribute('http.method', request.method);
    span.setAttribute('http.url', request.url);

    try {
      const response = await handleRequest(request, env, ctx);
      span.setAttribute('http.status_code', response.status);
      return response;
    } catch (err) {
      span.recordException(err);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw err;
    } finally {
      span.end();
    }
  },
};
```

## Verification
- **Test:** `test/observability.test.ts > metrics are emitted
  on every request` — passes
- **Live:** Dashboards show all key metrics
- **Audit:** Quarterly review of alerts + SLOs

## Gotchas
- **High-cardinality labels are expensive.** A label with
  millions of unique values (e.g. `userId` as a label) makes
  the metrics DB explode. Use logs/traces for high-cardinality
  data; metrics for low-cardinality aggregates.
- **The "alert on every error" anti-pattern.** You'll get
  paged for every transient error. Alert on trends, not
  individual events.
- **The "metrics are the source of truth" anti-pattern.**
  Metrics are sampled/aggregated. Logs are the raw truth.
- **The "no SLO" anti-pattern.** Without SLOs, you don't
  know if a metric is "good" or "bad."
- **The "no tracing" anti-pattern.** Logs tell you what
  happened; traces tell you where. For multi-service apps,
  traces are essential.

## Related
- `structured-logging.md`
- `tracing-distributed.md`
- `error-budget-slo.md`
- `safe-deploy-checklist.md`
- OpenTelemetry: https://opentelemetry.io/
- RED method: https://www.weave.works/blog/the-red-method-key-metrics-for-microservices-architecture/
- USE method: http://www.brendangregg.com/usemethod.html
- SRE workbook: https://sre.google/workbook/table-of-contents/
