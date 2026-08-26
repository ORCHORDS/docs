# grafana-datasource-config

**Issue:** Configuring data sources in Grafana via provisioning
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manually adding data sources through the UI is not reproducible across environments.

## Pattern / Solution
```yaml
# provisioning/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    jsonData:
      httpMethod: POST
      prometheusType: Prometheus
      prometheusVersion: 2.53.0

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    jsonData:
      derivedFields:
        - datasourceUid: tempo
          matcherRegex: '"trace_id":"(\w+)"'
          name: TraceID
          url: "$${__value.raw}"

  - name: Tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
```

## Gotchas
- `isDefault: true` can only be set on one data source
- Derived fields in Loki require matching the exact JSON field name
- Data source UIDs must be stable across environments for dashboard portability

## Related
- `grafana-setup.md`
- `grafana-loki-integration.md`
- `loki-log-labels.md`
