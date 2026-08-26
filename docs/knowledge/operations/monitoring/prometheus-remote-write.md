# prometheus-remote-write

**Issue:** Shipping Prometheus metrics to long-term storage via remote write
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Local Prometheus storage is insufficient for long-term retention or multi-region querying. Remote write sends data to Thanos, Cortex, Mimir, or cloud providers.

## Pattern / Solution
```yaml
# prometheus.yml
remote_write:
  - url: https://mimir.internal/api/v1/push
    basic_auth:
      username: prometheus
      password_file: /etc/prometheus/remote_write_password
    queue_config:
      capacity: 10000
      max_shards: 30
      min_shards: 1
      max_samples_per_send: 5000
      batch_send_deadline: 5s
    write_relabel_configs:
      - source_labels: [__name__]
        regex: go_.*
        action: drop  # drop noisy Go runtime metrics
```

Monitor remote write health:
```promql
# WAL replay lag
prometheus_remote_storage_samples_pending
prometheus_remote_storage_failed_samples_total
```

## Gotchas
- Remote write adds latency; not a replacement for local alerting
- Tune `max_shards` based on network bandwidth, not CPU
- `write_relabel_configs` runs after scrape relabeling; use to filter before shipping

## Related
- `prometheus-cardinality-management.md`
- `prometheus-setup-basics.md`
