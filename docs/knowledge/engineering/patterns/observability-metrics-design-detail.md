# observability-metrics-design-detail

**Issue:** Design metrics that answer real questions
**Date:** 2026-08-09
**Status:** documented

## Symptom
You instrument your app. You have 100 metrics. You don't
know which to look at. The dashboard is overwhelming. An
incident happens. You can't find the relevant metric.

## Root cause
**Metrics without purpose are noise.** Every metric should
answer a question.

**Source:** Google SRE book:
https://sre.google/sre-book/monitoring-distributed-systems/

> "Metrics should be designed to answer specific
> questions. ... A metric without a question is just a
> number."

## The "metric purpose" framework

For each metric, answer:
- **What question does it answer?**
- **Who will look at it?**
- **What action will they take?**

If you can't answer these, don't add the metric.

### Example: "What's the user experience?"
- **Metric:** `http_request_duration_seconds` (p50, p95, p99)
- **Owner:** The on-call
- **Action:** If p99 > 500ms, investigate the slow path

### Example: "Are we within SLO?"
- **Metric:** `service_requests_error_rate` (5xx / total)
- **Owner:** The on-call
- **Action:** If > 1%, page

## The "metric type" choice

### Counter
- **What:** Monotonically increasing value
- **Use:** Request count, error count, bytes sent
- **Example:** `http_requests_total{method="GET", status="200"}`

### Gauge
- **What:** Value that goes up and down
- **Use:** Memory usage, queue depth, active connections
- **Example:** `worker_memory_used_bytes`

### Histogram
- **What:** Distribution of values
- **Use:** Latency, request size
- **Example:** `http_request_duration_seconds_bucket{le="0.1"}`

### Summary
- **What:** Pre-computed quantiles
- **Use:** Quantiles over a window
- **Example:** `http_request_duration_seconds{quantile="0.99"}`

## The "RED method" applied

For each service:
```ts
// Rate
metrics.increment('service_requests_total', { service: 'user-service', endpoint: '/api/users' });

// Errors
metrics.increment('service_requests_failed_total', { service: 'user-service', endpoint: '/api/users', error_code: 'INVALID_EMAIL' });

// Duration
metrics.histogram('service_request_duration_seconds', duration, { service: 'user-service', endpoint: '/api/users' });
```

## The "USE method" applied

For each resource:
```ts
// Utilization
metrics.gauge('d1_storage_used_bytes', storageUsed);
metrics.gauge('worker_memory_used_bytes', memoryUsed);

// Saturation
metrics.gauge('queue_depth', queueDepth);
metrics.gauge('db_connection_pool_used', poolUsed);

// Errors
metrics.increment('d1_query_errors_total', { error_code: 'TIMEOUT' });
```

## The "high-cardinality" gotcha

Each label adds a dimension to the metric. High-cardinality
labels (e.g. `userId`) explode the storage:
```ts
// ❌ Bad: userId as a label
metrics.increment('user_actions_total', { userId: 'u_123' });
// 1M users = 1M label combinations

// ✅ Good: aggregate first
metrics.increment('user_actions_total', { action: 'login' });
// 1 label combination
```

For per-user data, use **logs** (not metrics):
```ts
// Logs (high-cardinality)
console.log({ message: 'user.login', userId: 'u_123' });
```

## The "metric naming" convention

Prometheus convention:
- **Lowercase + underscores**
- **Unit suffix:** `_seconds`, `_bytes`, `_total`
- **Describe what:** `http_requests_total`, not `requests`

```ts
metrics.increment('http_requests_total', { method: 'GET', status: '200' });
metrics.histogram('http_request_duration_seconds', duration);
metrics.gauge('worker_memory_used_bytes', memoryUsed);
```

## The "alert design" pattern

Alert when:
- **SLO breach** (e.g. error rate > 1% for 5 min)
- **Error budget exhausted** (no more room to fail)
- **Saturation** (DB at 90% capacity)
- **Anomaly** (sudden spike in errors)

Don't alert when:
- **A single error** (transient; no action needed)
- **A specific user has a problem** (use support)
- **A slow but expected operation** (a daily job that takes
  1 hour is normal)

```ts
// Alert: error rate > 1% for 5 min
if (errorRate > 0.01) {
  pageOncall('High error rate', { rate: errorRate });
}

// Alert: p99 latency > 500ms for 5 min
if (p99Latency > 500) {
  pageOncall('High latency', { p99: p99Latency });
}
```

## The "SLO" pattern

For each service, define SLOs:
- **Availability:** 99.9% of requests succeed
- **Latency:** 99% of requests are < 200ms
- **Freshness:** Data is < 1 min old

```ts
const sloTargets = {
  availability: 0.999,  // 99.9%
  latency: { p99: 200, percentile: 0.99 },
  freshness: 60_000,  // 1 min
};
```

## The "error budget" pattern

The error budget is `1 - SLO`:
- **SLO 99.9%:** budget = 0.1% (43 min downtime/month)
- **SLO 99%:** budget = 1% (7.2 hours downtime/month)

When the budget is exhausted, freeze deploys and fix the
bug.

```ts
const errorBudget = 1 - actualSlo;
if (errorBudget <= 0) {
  freezeDeploys();
}
```

## The "dashboard" pattern

For each service, a dashboard with:
- **RED metrics** (Rate, Errors, Duration)
- **USE metrics** (Utilization, Saturation, Errors)
- **SLO compliance**
- **Recent deploys**
- **Recent alerts**

The dashboard is the single source of truth for service
health.

## The "anomaly detection" pattern

For complex metrics, use anomaly detection:
```ts
// Datadog: "Watchdog" automatically detects anomalies
// Or: simple threshold + comparison to historical average
const currentErrorRate = getCurrentErrorRate();
const historicalAverage = getHistoricalAverage('error_rate', 7);  // 7-day average
if (currentErrorRate > historicalAverage * 2) {
  alert('Anomalous error rate', { current: currentErrorRate, average: historicalAverage });
}
```

## The "metric aggregation" pattern

For long-term storage, aggregate:
```ts
// At 1 minute: high-resolution metrics
// At 1 hour: aggregated (avg, max, p99)
// At 1 day: further aggregated
```

Most time-series DBs do this automatically (e.g.
Prometheus downsampling).

## The "CF Workers Analytics Engine" pattern

For high-cardinality, low-cost metrics:
```ts
// In a Worker
const event = {
  blobs: [userId, action],  // Indexed
  doubles: [duration],  // Numeric
  indexes: [tenantId],  // Indexed for query
};
env.ANALYTICS.writeDataPoint(event);
```

The Analytics Engine is designed for high-volume, high-
cardinality data (1M+ events/day).

## Verification
- **Test:** Metrics are emitted on every request
- **Live:** Dashboards are visible + alerts are configured
- **Audit:** Quarterly review of metrics + alerts

## Gotchas
- **The "100 metrics, 0 questions" anti-pattern.** Every
  metric must answer a question.
- **The "high-cardinality label" anti-pattern.** Labels
  with millions of values explode the storage.
- **The "no SLO" anti-pattern.** Without SLOs, you don't
  know if a metric is good or bad.
- **The "alert on every change" anti-pattern.** You'll
  get paged for every transient blip. Alert on trends.
- **The "metric for the sake of metric" anti-pattern.**
  Adding metrics is easy; understanding them is hard.
  Focus on the few that matter.

## Related
- `observability-three-pillars-detail.md`
- `error-budget-slo.md`
- `safe-deploy-checklist.md`
- `structured-logging.md`
- Prometheus: https://prometheus.io/docs/concepts/metric_types/
- SRE book: https://sre.google/sre-book/monitoring-distributed-systems/
- RED method: https://www.weave.works/blog/the-red-method-key-metrics-for-microservices-architecture/
