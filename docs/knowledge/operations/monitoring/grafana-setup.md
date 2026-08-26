# grafana-setup

**Issue:** Initial Grafana installation and configuration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams need a visualization layer on top of Prometheus and other data sources.

## Pattern / Solution
```yaml
# docker-compose.yml
services:
  grafana:
    image: grafana/grafana:11.1.0
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_SERVER_ROOT_URL: https://grafana.example.com
      GF_AUTH_GENERIC_OAUTH_ENABLED: "true"
      GF_AUTH_GENERIC_OAUTH_CLIENT_ID: ${OAUTH_CLIENT_ID}
      GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET}
      GF_SMTP_ENABLED: "true"
      GF_SMTP_HOST: smtp.example.com:587
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    ports:
      - "3000:3000"
```

Provision dashboards as code:
```yaml
# provisioning/dashboards/default.yml
apiVersion: 1
providers:
  - name: default
    folder: Provisioned
    type: file
    options:
      path: /etc/grafana/dashboards
```

## Gotchas
- Default admin password must be changed on first login
- Provisioned dashboards cannot be edited via UI without breaking IaC
- Use SMTP or PagerDuty for alert delivery; do not rely on Grafana email alone

## Related
- `grafana-datasource-config.md`
- `grafana-alerts-setup.md`
- `grafana-oncall-integration.md`
