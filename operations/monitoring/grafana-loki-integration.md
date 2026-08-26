# grafana-loki-integration

**Issue:** Connecting Loki to Grafana for log exploration and log-based alerts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Logs live in Loki but cannot be searched or correlated with metrics in Grafana dashboards.

## Pattern / Solution
Configure Loki datasource with trace correlation (see `grafana-datasource-config.md`), then use Explore view:

```logql
# Basic service log query
{env="prod", service="api"} | json | status >= 500

# Rate of errors panel
sum by (service) (rate({env="prod"} | json | level="error" [5m]))
```

Dashboard panel using logs:
- Panel type: **Logs**
- Query: `{job="$service"} | json | level=~"$level"`
- Enable "Dedup" to collapse repeated lines

Link logs to traces via derived fields — Grafana automatically converts `trace_id` values to clickable Tempo links.

## Gotchas
- Loki is not designed for full-text search; label matching is fast, grep-style searches are slow
- Log volume panels require `count_over_time` not `rate`
- Grafana log panel max lines defaults to 1000; increase for high-volume debugging

## Related
- `loki-logql-queries.md`
- `grafana-datasource-config.md`
- `loki-log-labels.md`
