# feature-cookbook-monitoring

**Issue:** Monitoring recipes — metrics, logs, traces, alerts
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your service is down. Users are tweeting. You don't know
until a customer emails you. The downtime was 30 minutes.
You wish you'd known earlier.

## Root cause
**Monitoring is the early warning system.** Without it,
you fly blind.

**Source:** Google SRE book:
https://sre.google/sre-book/monitoring-distributed-systems/

## The "RED method" pattern

For each service, track:
- **Rate:** Requests per second
- **Errors:** Failed requests per second
- **Duration:** Latency distribution

```ts
const start = Date.now();
try {
  const result = await handleRequest(request, env);
  const duration = (Date.now() - start) / 1000;
  metrics.histogram('http_request_duration_seconds', duration, {
    method: request.method,
    path: new URL(request.url).pathname,
    status: result.status,
  });
  metrics.increment('http_requests_total', {
    method: request.method,
    path: new URL(request.url).pathname,
    status: result.status,
  });
  return result;
} catch (err) {
  const duration = (Date.now() - start) / 1000;
  metrics.histogram('http_request_duration_seconds', duration, {
    method: request.method,
    path: new URL(request.url).pathname,
    status: 500,
  });
  metrics.increment('http_requests_total', {
    method: request.method,
    path: new URL(request.url).pathname,
    status: 500,
  });
  throw err;
}
```

Every request is instrumented.

## The "USE method" pattern

For each resource (DB, queue, cache):
- **Utilization:** % of resource used
- **Saturation:** Queue depth
- **Errors:** Error count

```ts
// D1
const d1Result = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind('u_123').first();
metrics.histogram('d1_query_duration_seconds', duration, { query: 'get_user' });
metrics.gauge('d1_storage_bytes', storageBytes);

// KV
const kvStart = Date.now();
const value = await env.KV.get('key');
metrics.histogram('kv_operation_duration_seconds', (Date.now() - kvStart) / 1000, { op: 'get' });
```

Every resource is monitored.

## The "alert" pattern

For alerts, use the "burn rate" approach:
```ts
// Page on-call if error budget is being burned too fast
const errorRate = errors / total;
const slo = 0.99;  // 99%
const fastBurn = 14.4;  // 2% budget in 1h
const slowBurn = 1;  // 10% budget in 3d

if (errorRate > slo + (1 - slo) * fastBurn) {
  pageOncall('Fast burn on error budget', { rate: errorRate });
} else if (errorRate > slo + (1 - slo) * slowBurn) {
  pageOncall('Slow burn on error budget', { rate: errorRate });
}
```

The alert is based on SLO burn rate.

## The "dashboard" pattern

For a service dashboard:
- **Top row:** RED metrics (Rate, Errors, Duration)
- **Second row:** USE metrics (CPU, memory, DB)
- **Third row:** Business metrics (DAU, conversion)
- **Fourth row:** Recent deploys + alerts
- **Fifth row:** Logs / traces

The dashboard is the source of truth.

## The "log aggregation" pattern

For logs, use a structured format:
```ts
logEvent('user.login', 'info', {
  userId: ctx.user.id,
  tenantId: ctx.tenant.id,
  method: 'password',
  ip: ctx.request.headers.get('cf-connecting-ip'),
  userAgent: ctx.request.headers.get('user-agent'),
});
```

The log is JSON; it's queryable in Datadog / Splunk.

## The "log levels" pattern

For log levels:
- **debug:** Verbose, off in production
- **info:** Normal events
- **warn:** Something unexpected
- **error:** Something failed
- **fatal:** System is broken

```ts
if (process.env.NODE_ENV === 'production') {
  log.setLevel('info');
} else {
  log.setLevel('debug');
}
```

The level controls the verbosity.

## The "trace" pattern

For distributed tracing:
```ts
import { trace, SpanStatusCode } from '@opentelemetry/api';

const tracer = trace.getTracer('my-app');

const span = tracer.startSpan('handleRequest', {
  attributes: { 'http.method': request.method, 'http.url': request.url },
});

try {
  const result = await processRequest(request, env, span);
  span.setStatus({ code: SpanStatusCode.OK });
  return result;
} catch (err) {
  span.recordException(err as Error);
  span.setStatus({ code: SpanStatusCode.ERROR });
  throw err;
} finally {
  span.end();
}
```

The trace is sent to the backend.

## The "alert routing" pattern

For alerts, route to the right team:
```yaml
# Datadog / PagerDuty
- name: Service X is down
  service: service-x
  team: team-x
  escalation:
    - oncall: team-x-primary
    - oncall: team-x-secondary
- name: DB is slow
  service: db
  team: platform
  escalation:
    - oncall: platform-primary
```

The right team gets paged.

## The "alert deduplication" pattern

For deduplication, group similar alerts:
```yaml
# PagerDuty
dedup_key: "service-x:error-rate"
# All error rate alerts in 1 hour are grouped
```

The team gets one page, not 100.

## The "alert context" pattern

For context, include useful info:
```json
{
  "alert": "Error rate > 5%",
  "service": "user-service",
  "current_rate": 0.07,
  "slo": 0.99,
  "burn_rate": 7,
  "dashboard": "https://grafana/d/user-service",
  "logs": "https://datadoghq.com/logs?query=service:user-service",
  "traces": "https://datadoghq.com/apm/service/user-service",
  "runbook": "https://wiki/runbooks/user-service"
}
```

The on-call has everything they need.

## The "on-call rotation" pattern

For on-call, rotate:
```yaml
# PagerDuty
schedule: team-x-oncall
rotation: weekly
people:
  - alice
  - bob
  - charlie
  - dave
```

The on-call is fair; no one is always on.

## The "post-mortem" pattern

After a major incident, write a post-mortem:
```markdown
# Post-mortem: 2026-08-09 user-service outage

## Summary
30-minute outage due to a bad deploy. User-facing
error rate spiked to 30%.

## Timeline
- 14:30 - Deploy v1.2.3
- 14:35 - Error rate alerts
- 14:40 - IC declared SEV-1
- 14:45 - Rollback started
- 14:55 - Rollback complete; error rate back to normal
- 15:00 - Post-mortem started

## Root cause
The deploy included a migration that wasn't
backward-compatible. Old code couldn't read the new
schema.

## Action items
- [ ] Add migration backward-compatibility check
- [ ] Add canary deploy for schema migrations
- [ ] Update deploy checklist
```

The post-mortem is blameless; the focus is the system.

## The "synthetic monitoring" pattern

For external monitoring, use a synthetic check:
```ts
// In a cron
export async function handleScheduled(event: ScheduledEvent, env: Env): Promise<void> {
  const checks = [
    { name: 'Homepage', url: 'https://example.com/', expectStatus: 200 },
    { name: 'API health', url: 'https://example.com/api/health', expectStatus: 200 },
    { name: 'Login', url: 'https://example.com/login', expectStatus: 200 },
  ];

  for (const check of checks) {
    const start = Date.now();
    const res = await fetch(check.url);
    const duration = Date.now() - start;

    if (res.status !== check.expectStatus) {
      await pageOncall('Synthetic check failed', { name: check.name, status: res.status });
    }

    metrics.histogram('synthetic.duration_ms', duration, { name: check.name });
  }
}
```

The synthetic check catches outages from the outside.

## The "error tracking" pattern

For error tracking, use Sentry:
```ts
import * as Sentry from '@sentry/browser';

Sentry.init({
  dsn: env.SENTRY_DSN,
  environment: env.ENVIRONMENT,
  release: env.RELEASE_VERSION,
  tracesSampleRate: 0.1,  // 10% of traces
  beforeSend(event) {
    // Strip PII
    if (event.user) {
      delete event.user.email;
      delete event.user.ip_address;
    }
    return event;
  },
});

try {
  // ... do work
} catch (err) {
  Sentry.captureException(err);
  throw err;
}
```

Errors are tracked; PII is stripped.

## Verification
- **Test:** Metrics are emitted
- **Live:** Dashboard is up to date
- **Audit:** Quarterly monitoring review

## Gotchas
- **The "alert on every change" anti-pattern.** You'll
  get paged for every transient blip. Alert on trends.
- **The "metric without action" anti-pattern.** Every
  metric should have an owner + an action.
- **The "PII in logs" anti-pattern.** A log with user
  emails is a GDPR issue. Strip PII.
- **The "log volume surprises" anti-pattern.** 1M users ×
  1 event/day = 1M log entries. Budget for it.
- **The "alerting without runbook" anti-pattern.** The
  on-call needs a runbook. Write one.
- **The "monitoring after the fact" anti-pattern.**
  Add monitoring when you add the feature, not after.

## Related
- `observability-three-pillars-detail.md`
- `observability-metrics-design-detail.md`
- `structured-logging.md`
- `error-budget-slo.md`
- `feature-observability-pattern.md`
- `feature-observability-tracing.md`
- `incident-response.md`
- SRE book: https://sre.google/sre-book/monitoring-distributed-systems/
