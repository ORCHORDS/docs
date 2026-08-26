# observability-metrics-design

**Issue:** What metrics to track + how to design them
**Date:** 2026-08-09
**Status:** documented

## Symptom
You add metrics to your app. You have 1000 different metrics.
No one knows what they mean. Dashboards are slow to load. The
on-call doesn't know which metric indicates which problem.

## Root cause
**Metrics design matters.** A bad metric name is a maintenance
burden. A high-cardinality metric is a storage cost.

**Source:** Google SRE — Monitoring Distributed Systems:
https://sre.google/sre-book/monitoring-distributed-systems/

> "The four golden signals are: latency, traffic, errors, and
> saturation."

## The 4 golden signals

For any service, track:

### 1. Latency
- **What:** How long requests take
- **Metric:** `request_duration_ms` (histogram)
- **Labels:** `endpoint`, `method`, `status_class` (2xx, 5xx)

### 2. Traffic
- **What:** How much demand on the service
- **Metric:** `request_count` (counter)
- **Labels:** `endpoint`, `method`

### 3. Errors
- **What:** Rate of requests failing
- **Metric:** `request_count` with `status_class=5xx` label
- **OR:** `error_count` (counter) + `error_rate` (computed)

### 4. Saturation
- **What:** How "full" the service is
- **Metric:** `cpu_usage`, `memory_usage`, `db_connections_used`
- **Labels:** `instance_id`, `region`

## The USE method (per resource)

For each resource (CPU, memory, disk, network, DB), track:
- **Utilization:** % time busy
- **Saturation:** queue length / wait time
- **Errors:** error count

## The RED method (per service)

For each service, track:
- **Requests:** count per second
- **Errors:** count per second (of failures)
- **Duration:** histogram of request latency

## The metric naming convention

`<namespace>_<subsystem>_<name>_<unit>`

Examples:
- `http_requests_total` (counter, request count)
- `http_request_duration_ms` (histogram, request latency)
- `db_query_duration_ms` (histogram, DB query latency)
- `auth_login_attempts_total` (counter, login attempts)
- `auth_login_failures_total` (counter, failed logins)

The unit suffix (`_total`, `_ms`, `_bytes`) makes the metric
self-documenting.

## Labels (dimensions)

Each metric has labels (key-value pairs):
- ✅ Use: `endpoint`, `method`, `status`, `region`, `tenant_id`
- ❌ Avoid: `user_id`, `request_id` (high cardinality)

High cardinality = many unique label combinations = expensive
storage + slow queries.

CF Analytics Engine has a soft limit on label combinations
per metric. Stay under 100 unique combinations per metric.

## The "what NOT to track" list

❌ **Don't track:**
- **User IDs as labels** (1M users = 1M combinations)
- **Request IDs as labels** (unbounded)
- **Email addresses as labels** (PII)
- **Free-form tags** (no consistency)

## The "what to track" checklist

For a consumer app:
- [ ] Request count by endpoint + status
- [ ] Request latency p50/p95/p99 by endpoint
- [ ] Error rate by endpoint + error kind
- [ ] DB query latency by query type
- [ ] Auth events (login, logout, failed login)
- [ ] Background job count + duration
- [ ] Queue depth (if using a queue)
- [ ] DO storage size (if using DOs)
- [ ] D1 read/write count by table
- [ ] KV get/put count
- [ ] R2 get/put count
- [ ] Cache hit rate (if using a cache)
- [ ] Rate limit hits (per tenant / per user)

## The alerting rules

For each metric, define an alert:
- **Error rate > 5% for 5 min** → page on-call
- **p99 latency > 1s for 5 min** → page on-call
- **Queue depth > 10k for 5 min** → warn
- **D1 errors > 1% for 1 min** → page on-call
- **SLO burn rate > 2x** → page on-call

## The "alerting on symptoms vs causes" principle

✅ Alert on **symptoms** (user-facing: error rate, latency)
❌ Don't alert on **causes** (CPU usage, memory usage — unless
they directly cause symptoms)

Cause-based alerts are noisy. Symptom-based alerts are
actionable.

## Verification
- **Test:** `test/metrics.test.ts > all metrics have names +
  labels + units` — passes
- **Live:** Dashboards load in < 2s
- **Audit:** Quarterly review of metric coverage

## Gotchas
- **Adding a metric is easy. Removing one is hard.** Old
  dashboards depend on the metric name. Use versioned names
  (`http_requests_v2`) when changing.
- **The metric name is a public API.** Don't break it
  without coordinating.
- **High cardinality is the silent killer.** A metric with
  `user_id` label and 1M users = 1M time series. Avoid.
- **Sampling affects metric accuracy.** If you sample logs
  at 10%, the metric computed from logs is also at 10%.
  Use a separate counter for metrics.
- **Metrics from logs vs native metrics.** Computing a
  metric from logs is more flexible but slower. Native metrics
  (e.g. Prometheus) are faster but require code changes.

## Related
- `observability-three-pillars.md` (logs + metrics + traces)
- `tracing-distributed.md` (traces for debugging)
- `error-budget-slo.md` (SLOs use metrics)
- Google SRE: https://sre.google/sre-book/monitoring-distributed-systems/
- USE method: https://www.brendangregg.com/usemethod.html
- RED method: https://www.weave.works/blog/the-red-method-key-metrics-for-microservices-architecture/
