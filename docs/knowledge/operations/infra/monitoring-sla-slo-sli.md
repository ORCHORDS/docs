# monitoring-sla-slo-sli

**Issue:** Defining and implementing SLAs, SLOs, and SLIs for service reliability measurement
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Vague reliability goals ("we want five nines"). No objective way to know if service is meeting reliability targets. Incidents debated without shared definition of "down".

## Pattern / Solution
Definitions:
```
SLI (Service Level Indicator): quantitative measure of service behavior
  e.g. "99th percentile HTTP latency over 1-minute window"

SLO (Service Level Objective): target for SLI
  e.g. "p99 latency < 500ms for 99.9% of 1-minute windows over 30 days"

SLA (Service Level Agreement): SLO + consequences (contract with customers)
  e.g. "If availability < 99.9% in a month, customer gets 10% credit"

Error Budget = 1 - SLO = allowed failure time
  99.9% availability SLO → 43.8 minutes/month of allowed downtime
```

Prometheus SLO recording rules:
```yaml
# Recording rules for availability SLO
groups:
- name: slo.api
  rules:
  - record: job:http_request_total:rate5m
    expr: rate(http_requests_total[5m])

  - record: job:http_errors_total:rate5m
    expr: rate(http_requests_total{status=~"5.."}[5m])

  - record: job:availability:rate5m
    expr: |
      1 - (
        job:http_errors_total:rate5m
        /
        job:http_request_total:rate5m
      )

  # Burn rate alert (error budget burning too fast)
  - alert: HighErrorBudgetBurn
    expr: |
      job:availability:rate5m < bool 1 - (14.4 * (1 - 0.999))
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "SLO error budget burning at 14.4× rate"
```

Multi-window burn rate alerts (Google approach):
```yaml
# Alert if burning >14.4x in 1h AND >1x in 6h (avoid false positives)
- alert: SLOBurnRateCritical
  expr: |
    (job:availability:rate1h < bool (1 - 14.4 * 0.001))
    and
    (job:availability:rate6h < bool (1 - 6 * 0.001))
```

## Gotchas
- SLOs should be aspirational but achievable — 100% is wrong (makes every outage a breach)
- Choose SLI that reflects user experience, not internal metrics (use request success rate, not CPU)
- Error budget policy must be agreed before an incident — who decides to halt features when budget is exhausted?
- SLOs need at least 30 days of data to be meaningful — pilot in shadow mode first

## Related
- `alerting-fatigue-reduction.md`
- `prometheus-alertmanager-config.md`
- `sre-error-budget-policy.md`
