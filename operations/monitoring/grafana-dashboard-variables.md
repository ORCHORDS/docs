# grafana-dashboard-variables

**Issue:** Using template variables in Grafana dashboards for dynamic filtering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dashboards hardcode environment or service names, requiring duplicate dashboards for each environment.

## Pattern / Solution
```json
// Dashboard JSON - variables section
{
  "templating": {
    "list": [
      {
        "name": "env",
        "type": "query",
        "query": "label_values(up, env)",
        "datasource": "Prometheus",
        "refresh": 2,
        "multi": false,
        "includeAll": false
      },
      {
        "name": "service",
        "type": "query",
        "query": "label_values(up{env=\"$env\"}, job)",
        "datasource": "Prometheus",
        "refresh": 2,
        "multi": true,
        "includeAll": true
      }
    ]
  }
}
```

Reference in panel queries:
```promql
rate(http_requests_total{env="$env", job=~"$service"}[5m])
```

## Gotchas
- Chained variables (service depends on env) must set `refresh: 2` (on time range change)
- `$__rate_interval` auto-adjusts to scrape interval; prefer over hardcoded `[5m]`
- Variables in alert queries are not supported; use recording rules instead

## Related
- `grafana-setup.md`
- `grafana-alerts-setup.md`
