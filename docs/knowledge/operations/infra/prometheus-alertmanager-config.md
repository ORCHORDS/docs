# prometheus-alertmanager-config

**Issue:** Structuring Prometheus alerting rules and Alertmanager routing to avoid alert fatigue
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Alerts fire and resolve every few minutes (flapping), on-call engineers are paged for non-actionable conditions, and critical alerts are buried in noise. Alert rules are duplicated across services with inconsistent thresholds.

## Pattern / Solution
Use recording rules to pre-compute expensive queries, route by severity, and group alerts to reduce notification volume.

**Recording rules (reduce query cost):**
```yaml
# rules/recording.yaml
groups:
  - name: aggregations
    interval: 30s
    rules:
      - record: job:request_duration_seconds:p99
        expr: histogram_quantile(0.99, sum by (job, le) (rate(http_request_duration_seconds_bucket[5m])))
      - record: job:error_rate
        expr: sum by (job) (rate(http_requests_total{status=~"5.."}[5m])) / sum by (job) (rate(http_requests_total[5m]))
```

**Alert rules:**
```yaml
# rules/alerts.yaml
groups:
  - name: slo
    rules:
      - alert: HighErrorRate
        expr: job:error_rate > 0.01
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on {{ $labels.job }}"
          description: "Error rate {{ $value | humanizePercentage }} > 1%"

      - alert: LatencyP99High
        expr: job:request_duration_seconds:p99 > 2
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "P99 latency > 2 s on {{ $labels.job }}"
```

**Alertmanager routing tree:**
```yaml
# alertmanager.yaml
global:
  resolve_timeout: 5m

route:
  group_by: [alertname, job]
  group_wait: 30s        # wait before sending first notification
  group_interval: 5m     # wait before sending new alerts in same group
  repeat_interval: 4h    # resend if still firing
  receiver: slack-default

  routes:
    - match:
        severity: critical
      receiver: pagerduty
      continue: true      # also sends to slack-default

    - match:
        severity: warning
      receiver: slack-warnings
      group_interval: 15m

inhibit_rules:
  - source_match:
      severity: critical
    target_match:
      severity: warning
    equal: [alertname, job]   # suppress warnings when critical is firing

receivers:
  - name: pagerduty
    pagerduty_configs:
      - routing_key: <pd-key>
  - name: slack-default
    slack_configs:
      - api_url: <webhook>
        channel: '#alerts'
        title: '{{ .CommonAnnotations.summary }}'
  - name: slack-warnings
    slack_configs:
      - api_url: <webhook>
        channel: '#alerts-warnings'
```

## Gotchas
- `for: 0m` fires immediately on first scrape; always use `for: 5m` or more to reduce flapping on transient spikes.
- `group_wait` is the delay before the first notification — set it low enough to be useful but high enough to batch related alerts.
- Recording rule intervals must be multiples of `scrape_interval`; mismatches cause gaps.
- `inhibit_rules` require the `equal` labels to be present on both source and target; missing labels mean inhibition never triggers.

## Related
- `grafana-dashboard-as-code.md`
- `opentelemetry-collector-config.md`
- `log-aggregation-loki.md`
