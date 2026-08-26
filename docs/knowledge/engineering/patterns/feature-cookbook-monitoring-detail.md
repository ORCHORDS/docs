# feature-cookbook-monitoring-detail

**Issue:** Monitoring — metrics, logs, traces, alerts
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your service is slow. Users complain. You don't know
where the bottleneck is. You check the logs. There's
nothing. You wish you had observability.

## Root cause
**Without monitoring, you're flying blind.** Use the
three pillars.

**Source:** Google SRE Book.

## The "three pillars" pattern

For observability:
1. **Metrics:** Numeric data (CPU, latency, error rate)
2. **Logs:** Event records (user signed up, payment
   failed)
3. **Traces:** Request flow across services

**Source:** Google SRE Book.

## The "metrics" pattern

For metrics, use a counter + gauge + histogram:
```ts
// Counter: increment only
metrics.increment('requests_total', { endpoint: '/api/users', status: '200' });
metrics.increment('requests_total', { endpoint: '/api/users', status: '500' });

// Gauge: set the value
metrics.gauge('queue_depth', depth, { queue: 'tasks' });
metrics.gauge('active_users', count);

// Histogram: distribution
metrics.histogram('latency_ms', duration, { endpoint: '/api/users' });
```

The metrics capture the system state.

## The "log" pattern

For structured logs:
```ts
logEvent('user.signup', 'info', {
  userId: user.id,
  email: user.email,
  source: 'web',
  durationMs: 123,
});
```

The log is structured.

## The "trace" pattern

For traces, span the request:
```ts
async function getUser(id: string, env: Env): Promise<User> {
  const span = tracer.startSpan('getUser', { attributes: { userId: id } });

  try {
    const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first<User>();
    span.setAttribute('user.found', !!user);
    return user!;
  } catch (err) {
    span.recordException(err as Error);
    throw err;
  } finally {
    span.end();
  }
}
```

The trace is captured.

## The "SLO" pattern

For SLO (Service Level Objective):
- **Availability:** 99.9% (3 nines = 8.7h/yr)
- **Latency:** p99 < 200ms
- **Error rate:** < 0.1%

```ts
const slo = {
  availability: 0.999,  // 99.9%
  latencyP99: 200,  // 200ms
  errorRate: 0.001,  // 0.1%
};
```

The SLO is the target.

## The "error budget" pattern

For error budget:
- **SLO:** 99.9% availability
- **Error budget:** 0.1% of requests can fail
- **Burn rate:** How fast the budget is consumed

If the error budget is exhausted, freeze deploys.

## The "alert" pattern

For alerts, by SLO:
- **Latency:** Alert if p99 > 500ms for 5 min
- **Error rate:** Alert if errors > 1% for 5 min
- **Uptime:** Alert if 5xx rate > 0.5% for 5 min
- **Saturation:** Alert if CPU > 80% for 10 min

```ts
async function checkAlerts(env: Env): Promise<void> {
  const errorRate = await getErrorRate(env);
  if (errorRate > 0.01) {
    await pageOnCall({ severity: 'critical', message: 'Error rate > 1%' });
  }
}
```

The alerts catch the issue.

## The "alert fatigue" pattern

For alert fatigue, prioritize:
- **Critical:** Page immediately (e.g. service down)
- **Warning:** Slack / email (e.g. latency high)
- **Info:** Dashboard (e.g. normal metrics)

Limit pages to < 1/day on average.

## The "dashboard" pattern

For a dashboard, the standard panels:
- **Request rate:** Per endpoint
- **Error rate:** Per endpoint
- **Latency:** p50, p95, p99
- **Saturation:** CPU, memory, queue depth
- **Business metrics:** Signups, revenue

The dashboard is the at-a-glance view.

## The "log levels" pattern

For log levels:
- **DEBUG:** Detailed flow (dev only)
- **INFO:** Notable events
- **WARN:** Recoverable issues
- **ERROR:** Failed operations
- **FATAL:** Service is broken

```ts
logEvent('payment.charged', 'info', { userId, amount });
logEvent('payment.failed', 'warn', { userId, reason: 'declined' });
logEvent('payment.error', 'error', { userId, error: String(err) });
```

The level is appropriate.

## The "log aggregation" pattern

For log aggregation:
- **CloudWatch:** AWS
- **Stackdriver:** GCP
- **Logflare:** CF-friendly
- **Datadog:** Cross-cloud

```ts
// Send to Logflare
await fetch('https://api.logflare.app/logs', {
  method: 'POST',
  headers: { 'x-api-key': env.LOGFLARE_KEY },
  body: JSON.stringify({ message, level, ...metadata }),
});
```

The logs are aggregated.

## The "distributed tracing" pattern

For distributed traces:
- **OpenTelemetry:** Vendor-neutral standard
- **Jaeger:** Open-source
- **Honeycomb:** SaaS
- **Datadog APM:** SaaS

```ts
import { trace } from '@opentelemetry/api';
const tracer = trace.getTracer('my-app');

const span = tracer.startSpan('handleRequest');
span.setAttribute('http.url', request.url);
span.setAttribute('http.method', request.method);
// ... do work
span.end();
```

The trace is captured across services.

## The "monitoring anti-pattern" anti-patterns

### 1. No monitoring
- **Issue:** Flying blind
- **Fix:** Three pillars

### 2. Alert on every metric
- **Issue:** Alert fatigue
- **Fix:** Alert on SLO

### 3. No SLO
- **Issue:** Don't know what's "bad"
- **Fix:** Define SLO

### 4. No dashboard
- **Issue:** Can't see the system
- **Fix:** Dashboard

### 5. PII in logs
- **Issue:** GDPR violation
- **Fix:** Redact PII

### 6. No correlation
- **Issue:** Can't follow a request
- **Fix:** Trace ID

## Verification
- **Test:** Metrics are collected
- **Test:** Logs are structured
- **Test:** Traces are captured
- **Live:** Alerts work
- **Audit:** Quarterly monitoring review

## Gotchas
- **The "no monitoring" anti-pattern.** Use three
  pillars.
- **The "no SLO" anti-pattern.** Define SLO.
- **The "PII in logs" anti-pattern.** Redact.
- **The "no correlation" anti-pattern.** Trace ID.

## Related
- `observability-three-pillars.md`
- `error-budget-slo.md`
- `feature-cookbook-monitoring.md`
- `feature-cookbook-incident-response.md`
- `feature-cookbook-debugging.md`
- `structured-logging.md`
- Google SRE Book: https://sre.google/sre-book/table-of-contents/
- OpenTelemetry: https://opentelemetry.io/
