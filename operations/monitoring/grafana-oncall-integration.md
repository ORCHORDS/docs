# grafana-oncall-integration

**Issue:** Integrating Grafana OnCall with Grafana Alerting for on-call routing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Alerts fire but no one is paged because the notification pipeline is not connected to on-call schedules.

## Pattern / Solution
1. Deploy Grafana OnCall (cloud or self-hosted):
```yaml
services:
  oncall:
    image: grafana/oncall:latest
    environment:
      SECRET_KEY: ${ONCALL_SECRET}
      DATABASE_HOST: postgres
      BROKER_TYPE: redis
```

2. Configure Grafana contact point:
```yaml
# provisioning/alerting/contact-points.yml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: OnCall
    receivers:
      - uid: oncall-webhook
        type: webhook
        settings:
          url: http://oncall:8080/integrations/v1/grafana/${INTEGRATION_TOKEN}/
```

3. Set notification policy to route critical alerts to OnCall contact point.

## Gotchas
- OnCall requires a separate Grafana API key with Editor role
- Alert grouping in notification policy affects how OnCall creates incidents
- Test the webhook with a manual alert before relying on it for production

## Related
- `grafana-alerts-setup.md`
- `on-call-rotation-setup.md`
- `pagerduty-integration.md`
