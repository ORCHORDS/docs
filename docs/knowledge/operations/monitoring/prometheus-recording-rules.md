# prometheus-recording-rules

**Issue:** Pre-computing expensive PromQL queries with recording rules
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dashboard queries are slow and alerting rules time out because complex aggregations run on every evaluation.

## Pattern / Solution
```yaml
# rules/recording.yml
groups:
  - name: slo_rules
    interval: 30s
    rules:
      - record: slo:burnrate5m
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          / sum(rate(http_requests_total[5m]))

      - record: slo:burnrate1h
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[1h]))
          / sum(rate(http_requests_total[1h]))

      - record: job:request_latency_seconds:p99
        expr: histogram_quantile(0.99, sum by (le, job) (rate(request_duration_seconds_bucket[5m])))
```

Reference recording rules in alerts:
```yaml
- alert: HighErrorRate
  expr: slo:burnrate1h > 0.01
```

## Gotchas
- Recording rule names must follow `level:metric:operation` convention
- Rules in the same group evaluate sequentially; split hot rules into separate groups
- Recording rules do not backfill historical data

## Related
- `slo-multi-window-alerting.md`
- `prometheus-alerting-rules.md`
