# kubernetes-observability-stack

**Issue:** Deploying the Prometheus/Grafana/Loki/Tempo observability stack on Kubernetes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Operating Kubernetes without observability is flying blind. The kube-prometheus-stack Helm chart provides metrics, alerting, and dashboards. Adding Loki for logs and Tempo for traces completes the three pillars.

## Pattern / Solution
Install kube-prometheus-stack:
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f observability-values.yaml
```

observability-values.yaml essentials:
```yaml
prometheus:
  prometheusSpec:
    retention: 15d
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: fast-ssd
          resources:
            requests:
              storage: 100Gi
    additionalScrapeConfigs:
    - job_name: myapp
      kubernetes_sd_configs:
      - role: pod
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: "true"

grafana:
  adminPassword: "change-me-via-secret"
  persistence:
    enabled: true
    size: 10Gi
  dashboardProviders:
    dashboardproviders.yaml:
      providers:
      - name: default
        folder: ''
        type: file
        options:
          path: /var/lib/grafana/dashboards
```

Add Loki for logs:
```bash
helm upgrade --install loki grafana/loki-stack \
  -n monitoring \
  --set loki.persistence.enabled=true \
  --set loki.persistence.size=50Gi \
  --set promtail.enabled=true
```

Add Tempo for traces:
```bash
helm upgrade --install tempo grafana/tempo -n monitoring
```

## Gotchas
- kube-prometheus-stack CRDs conflict on reinstall; save CRDs separately before upgrade
- Grafana datasources defined as ConfigMaps require pod restart after change
- Prometheus cardinality explosion (millions of unique label combinations) causes OOM; use `metric_relabel_configs` to drop high-cardinality labels
- Loki is optimized for streaming, not full-text search; use LogQL for structured queries
- PVC storage for Prometheus must be in the same AZ as the Prometheus pod

## Related
- `slo-alerting-thresholds.md`
- `post-deploy-monitoring-checklist.md`
- `kubernetes-service-mesh-istio.md`
- `synthetic-monitoring-deploy.md`
