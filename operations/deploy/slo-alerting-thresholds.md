# slo-alerting-thresholds

**Issue:** How to set alert thresholds from SLO error budgets so alerts fire at the right time
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams either alert too eagerly (alert fatigue) or too late (SLO already breached before alert fires). Threshold-setting from error budgets produces alerts that are calibrated to actual user impact.

## Pattern / Solution
**Burn-rate alerting (Google SRE model)**
Alert when the current error rate will exhaust the monthly error budget in X hours.

```
burn_rate = current_error_rate / (1 - SLO_target)

# Example: 99.9% availability SLO = 0.1% error budget
# 1-hour error rate of 1% burns budget at rate:
burn_rate = 0.01 / 0.001 = 10x
# At 10x burn rate, budget exhausted in: 30 days / 10 = 3 days
```

**Recommended multi-window alert (Prometheus / Alertmanager)**
```yaml
groups:
  - name: slo_alerts
    rules:
      # Fast burn — critical (will exhaust budget in ~1 hour)
      - alert: ErrorBudgetFastBurn
        expr: |
          (
            rate(http_requests_total{status=~"5.."}[5m]) /
            rate(http_requests_total[5m])
          ) > 14.4 * 0.001
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Fast error budget burn (14.4x rate)"

      # Slow burn — warning (will exhaust budget in ~3 days)
      - alert: ErrorBudgetSlowBurn
        expr: |
          (
            rate(http_requests_total{status=~"5.."}[30m]) /
            rate(http_requests_total[30m])
          ) > 3 * 0.001
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Slow error budget burn (3x rate)"
```

**Latency SLO alert**
```yaml
- alert: LatencyBudgetBurn
  expr: |
    histogram_quantile(0.99,
      rate(http_request_duration_seconds_bucket[5m])
    ) > 1.0
  for: 5m
  labels:
    severity: warning
```

## Gotchas
- Short windows (1m) produce noisy alerts from traffic spikes; use 5m minimum
- Always alert on burn rate, not raw error count — traffic volume changes the meaning of a count
- SLO targets must be agreed with the business, not picked by engineering alone
- Set an "SLO breach imminent" alert at 50% budget consumed with 10 days remaining

## Related
- `on-call-escalation-policy.md`
- `post-deploy-monitoring-checklist.md`
- `datadog-vs-prometheus-2026.md`
