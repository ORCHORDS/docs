# log-aggregation-loki

**Issue:** Deploying Grafana Loki for cost-effective log aggregation without full-text indexing overhead
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Elasticsearch or CloudWatch log storage costs grow linearly with log volume. Teams need to query logs alongside metrics and traces in a single tool. Loki's label-based approach is cheaper but its cardinality constraints are violated, causing performance issues.

## Pattern / Solution
Ship logs via Promtail or OpenTelemetry Collector, use low-cardinality labels, and query with LogQL.

**Loki config (`loki-config.yaml`):**
```yaml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: s3
      schema: v13
      index:
        prefix: loki_index_
        period: 24h

storage_config:
  tsdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/cache
  aws:
    s3: s3://my-loki-bucket/loki
    region: us-east-1

limits_config:
  ingestion_rate_mb: 16
  ingestion_burst_size_mb: 32
  max_label_names_per_series: 15   # keep labels low-cardinality
  retention_period: 30d
```

**Promtail config (`promtail-config.yaml`):**
```yaml
clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: kubernetes-pods
    kubernetes_sd_configs:
      - role: pod
    pipeline_stages:
      - json:
          expressions:
            level: level
            message: msg
      - labels:
          level:
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        target_label: app
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
```

**LogQL queries:**
```logql
# Error rate from a specific service
sum(rate({app="api", namespace="production"} |= "error" [5m])) by (app)

# Extract latency from structured JSON logs
{app="api"} | json | latency_ms > 500

# Count log lines by level
sum by (level) (count_over_time({namespace="production"}[1h]))

# Grep with regex
{app="api"} |~ "timeout|connection refused"
```

## Gotchas
- High-cardinality labels (user ID, request ID, trace ID) destroy Loki's performance — put those values in the log line body, not as labels.
- Loki does not reorder out-of-sequence log entries per stream; if your app emits logs with non-monotonic timestamps, queries may miss entries.
- The default `max_entries_limit_per_query` is 5000 lines; paginate with `--limit` in LogQL or increase for analytical queries.
- S3 object storage requires eventual consistency — newly ingested logs may not be queryable for a few seconds.

## Related
- `opentelemetry-collector-config.md`
- `prometheus-alertmanager-config.md`
- `grafana-dashboard-as-code.md`
