# prometheus-scrape-config

**Issue:** Configuring Prometheus scrape jobs to collect metrics from targets
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Metrics are not appearing in Prometheus because scrape jobs are misconfigured or targets are unreachable.

## Pattern / Solution
```yaml
scrape_configs:
  - job_name: node-exporter
    static_configs:
      - targets:
          - node1.internal:9100
          - node2.internal:9100
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance

  - job_name: my-api
    metrics_path: /metrics
    scheme: https
    tls_config:
      insecure_skip_verify: false
    static_configs:
      - targets: [api.example.com:443]

  # Kubernetes service discovery
  - job_name: k8s-pods
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: "true"
```

## Gotchas
- `metrics_path` defaults to `/metrics`; override for non-standard paths
- Scrape timeout must be less than scrape interval
- Use `honor_labels: true` only when targets set their own job/instance labels

## Related
- `prometheus-setup-basics.md`
- `prometheus-labels-best-practices.md`
