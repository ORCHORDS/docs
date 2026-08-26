# grafana-alerts-setup

**Issue:** Configuring Grafana Unified Alerting for multi-datasource alerts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams need alerts from Grafana dashboards that go beyond Prometheus Alertmanager capabilities, including Loki log-based alerts.

## Pattern / Solution
```yaml
# provisioning/alerting/rules.yml
apiVersion: 1
groups:
  - orgId: 1
    name: API Alerts
    folder: Alerts
    interval: 1m
    rules:
      - uid: api-error-rate
        title: High API Error Rate
        condition: C
        data:
          - refId: A
            datasourceUid: prometheus
            model:
              expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
          - refId: C
            datasourceUid: __expr__
            model:
              type: threshold
              conditions:
                - evaluator:
                    params: [0.05]
                    type: gt
```

Contact points and notification policies must also be provisioned in `provisioning/alerting/`.

## Gotchas
- Unified Alerting replaced the legacy dashboard alerts in Grafana 9+
- Alerts fire per evaluation period, not on data gaps; configure `No Data` behavior explicitly
- Contact points can be tested from the UI before going live

## Related
- `grafana-oncall-integration.md`
- `prometheus-alerting-rules.md`
- `alert-severity-levels.md`
