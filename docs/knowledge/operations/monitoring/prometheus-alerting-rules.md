# prometheus-alerting-rules

**Issue:** Writing effective Prometheus alerting rules
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Alerts fire spuriously or too late because rules lack proper thresholds, for-durations, or labels.

## Pattern / Solution
```yaml
# rules/alerts.yml
groups:
  - name: api_alerts
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          / sum(rate(http_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "High error rate on {{ $labels.job }}"
          description: "Error rate is {{ $value | humanizePercentage }} over last 5m"
          runbook: "https://wiki.internal/runbooks/high-error-rate"

      - alert: InstanceDown
        expr: up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Instance {{ $labels.instance }} is down"
```

## Gotchas
- Always include a `for` duration to avoid flapping alerts
- Use `$labels` and `$value` in annotations for context
- Group related alerts so Alertmanager can deduplicate them
- Test expressions in Prometheus UI before adding to rules file

## Related
- `prometheus-recording-rules.md`
- `alert-severity-levels.md`
- `alerting-runbook-linking.md`
