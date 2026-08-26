# prometheus-setup-basics

**Issue:** Initial Prometheus setup and configuration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams need a working Prometheus instance to collect metrics from services and infrastructure.

## Pattern / Solution
```yaml
# docker-compose.yml
services:
  prometheus:
    image: prom/prometheus:v2.53.0
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=15d
      - --web.enable-lifecycle
    ports:
      - "9090:9090"
volumes:
  prometheus_data:
```

```yaml
# prometheus.yml minimal config
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: [localhost:9090]
```

Reload config without restart: `curl -X POST http://localhost:9090/-/reload`

## Gotchas
- Default retention is 15 days; increase `--storage.tsdb.retention.size` for longer
- Enable `--web.enable-lifecycle` for hot reloads
- Do not expose Prometheus publicly without authentication

## Related
- `prometheus-scrape-config.md`
- `prometheus-alerting-rules.md`
- `grafana-datasource-config.md`
