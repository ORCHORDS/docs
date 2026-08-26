# Golden Signals Monitoring

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team has hundreds of dashboards and thousands of metrics but cannot
answer the basic question: "Is the service healthy right now?" Alert fatigue
is high because alerts fire on symptoms (CPU, memory) rather than user-facing
impact. Incidents are detected by customer complaints, not monitoring.

## Context

The Four Golden Signals are a prioritization framework from the Google SRE
book (Chapter 6) that answers: "If you can only measure four things about
your service, what should they be?" The answer is latency, traffic, errors,
and saturation. These four signals tell you whether your service is healthy
from the user's perspective and are the foundation on which SLOs, error
budgets, and burn-rate alerts are built.

## The four signals

### 1. Latency
The time it takes to serve a request. Measure successful requests separately
from failed requests — a fast error is not a sign of health.

- **Metric:** `http_request_duration_seconds` (histogram)
- **Alert on:** p99 latency, not average. Average hides tail latency.
- **Dashboard:** p50, p90, p95, p99 latency over time, broken by endpoint.
- **Common mistake:** alerting on average latency. A p50 of 50ms with a p99
  of 5s looks "fine" at the average but means 1% of users wait 100x longer.

### 2. Traffic
The demand being placed on your service. For HTTP services, requests per
second. For a database, queries per second. For a streaming system, messages
per second.

- **Metric:** `http_requests_total` (counter, rate)
- **Alert on:** sudden drop (outage signal) or sudden spike (attack/viral).
- **Dashboard:** RPS over time, broken by endpoint and status code class.
- **Common mistake:** alerting on absolute RPS. Use percentage-based anomaly
  detection — "50% drop in traffic" is more meaningful than "< 100 RPS."

### 3. Errors
The rate of requests that fail. Distinguish explicit errors (HTTP 5xx),
implicit errors (200 OK with wrong content), and policy errors (responses
slower than SLO).

- **Metric:** `http_requests_total{status=~"5.."}` / `http_requests_total`
- **Alert on:** error rate, not error count. 100 errors at 10K RPS is fine;
  100 errors at 200 RPS is a crisis.
- **Dashboard:** error rate over time, broken by status code and endpoint.
- **Common mistake:** only counting 5xx. A 200 response with `{"error":
  "internal failure"}` is an error your HTTP metrics won't catch. Instrument
  application-level error signals.

### 4. Saturation
How "full" your service is. Which resource will exhaust first? CPU, memory,
disk I/O, file descriptors, connection pool, goroutine/thread count.

- **Metric:** resource utilization as a percentage of capacity.
- **Alert on:** rate of change, not current value. 70% CPU is fine if
  stable; 70% CPU growing 5% per hour will exhaust in 6 hours.
- **Dashboard:** top-N saturated resources, projected time to exhaustion.
- **Common mistake:** alerting on current saturation only. By the time you
  alert at 90%, it is too late. Alert on the rate of saturation increase.

## Implementation with OpenTelemetry + Prometheus

```yaml
# Prometheus recording rules for golden signals
groups:
  - name: golden_signals
    rules:
      # Latency: p99 over 5 minutes
      - record: svc:http_request_duration:p99_5m
        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

      # Traffic: requests per second
      - record: svc:http_requests:rate5m
        expr: sum(rate(http_requests_total[5m])) by (service)

      # Error rate
      - record: svc:http_error_rate:ratio5m
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
          /
          sum(rate(http_requests_total[5m])) by (service)

      # Saturation: CPU
      - record: svc:cpu_utilization:avg5m
        expr: avg(rate(process_cpu_seconds_total[5m])) by (service)
```

## Golden Signals vs. RED vs. USE

| Framework | Signals | Scope | When to use |
|---|---|---|---|
| **Golden Signals** | Latency, Traffic, Errors, Saturation | Service-level | Default for SRE — covers both request and resource health |
| **RED** | Rate, Errors, Duration | Request-level | Microservices with request-driven workloads |
| **USE** | Utilization, Saturation, Errors | Resource-level | Infrastructure and capacity planning |

Golden Signals is a superset: it combines RED's request focus (Latency ≈
Duration, Traffic ≈ Rate, Errors ≈ Errors) with USE's resource focus
(Saturation). Use Golden Signals as the default; use RED or USE when you need
a narrower lens.

## Anti-patterns

- **Dashboard sprawl without golden signals** — 50 dashboards for one
  service but no single view answering "is it healthy?" Start with golden
  signals, then drill down.
- **Alerting on infrastructure, not golden signals** — "CPU > 80%" is a
  capacity signal, not a user impact signal. Alert on latency and error rate
  first; use saturation for capacity planning.
- **Missing the "implicit error" signal** — only counting HTTP 5xx misses
  business logic errors returned as 200 OK.

## Gotchas

- **Histogram bucket boundaries matter** — choose buckets that match your
  SLO thresholds. Default Prometheus buckets (5ms to 10s) may not align with
  your latency targets.
- **Saturation is service-specific** — for a database, saturation is
  connection pool utilization. For a queue consumer, it is queue depth. For a
  disk-heavy service, it is I/O wait. Identify your service's bottleneck
  resource.
- **Cardinality explosion** — breaking golden signals by endpoint × method ×
  status code × instance can create millions of time series. Use recording
  rules to pre-aggregate.

## Verification

- Your team can answer "is the service healthy?" in under 10 seconds by
  looking at one dashboard.
- Every alert is tied to a golden signal, not a raw infrastructure metric.
- MTTR improves within 60 days of implementation (industry benchmark: up to
  60% reduction).
- On-call engineers start triage from the golden signals dashboard, not from
  raw logs.

## Related

- `documentation/docs/policies/monitoring/red-use-metrics-framework.md`
- `documentation/docs/policies/monitoring/sli-slo-sla-definitions.md`
- `documentation/docs/policies/monitoring/multiwindow-burn-rate-slo-alerts.md`
- `documentation/docs/policies/monitoring/prometheus-recording-rules.md`

## Source URLs (verified 2026-08-16)

- Google SRE book: Monitoring Distributed Systems — https://sre.google/sre-book/monitoring-distributed-systems/
- How to implement four golden signals — https://oneuptime.com/blog/post/2026-02-20-monitoring-golden-signals/view
- SRE golden signals guide — https://autoheal.ai/learn/sre-golden-signals-guide
- Four golden signals of SRE — https://pagertree.com/learn/devops/what-is-site-reliability-engineering-sre/four-golden-signals-sre-monitoring
- Four golden signals complete guide 2026 — https://novaaiops.com/golden-signals
