# opentelemetry-collector-config

**Issue:** Deploying and configuring the OpenTelemetry Collector as a centralized telemetry pipeline
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications send traces, metrics, and logs directly to backends (Jaeger, Prometheus, Loki). Changing backends requires code changes. Telemetry volume is unconstrained and overwhelms backends. Sampling logic is inconsistent across services.

## Pattern / Solution
Route all telemetry through a Collector that handles batching, filtering, sampling, and fan-out.

**Minimal collector config (`otel-config.yaml`):**
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

  # Scrape Prometheus metrics from the host
  prometheus:
    config:
      scrape_configs:
        - job_name: 'otel-collector'
          static_configs:
            - targets: ['localhost:8888']

processors:
  batch:
    timeout: 5s
    send_batch_size: 1000

  memory_limiter:
    check_interval: 1s
    limit_mib: 512

  # Probabilistic sampling — keep 10% of traces
  probabilistic_sampler:
    sampling_percentage: 10

  # Always keep error traces
  filter/errors:
    error_mode: ignore
    traces:
      span:
        - 'attributes["http.status_code"] >= 500'

  resource:
    attributes:
      - key: deployment.environment
        value: production
        action: upsert

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true

  prometheusremotewrite:
    endpoint: http://prometheus:9090/api/v1/write

  loki:
    endpoint: http://loki:3100/loki/api/v1/push

  debug:
    verbosity: basic     # log pipeline activity to stdout

service:
  pipelines:
    traces:
      receivers:  [otlp]
      processors: [memory_limiter, probabilistic_sampler, batch]
      exporters:  [otlp/tempo]

    metrics:
      receivers:  [otlp, prometheus]
      processors: [memory_limiter, batch]
      exporters:  [prometheusremotewrite]

    logs:
      receivers:  [otlp]
      processors: [memory_limiter, batch, resource]
      exporters:  [loki]
```

**Kubernetes deployment (DaemonSet for node-level collection):**
```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-collector
spec:
  template:
    spec:
      containers:
        - name: collector
          image: otel/opentelemetry-collector-contrib:0.104.0
          args: ["--config=/conf/otel-config.yaml"]
          ports:
            - containerPort: 4317   # OTLP gRPC
            - containerPort: 4318   # OTLP HTTP
          volumeMounts:
            - name: config
              mountPath: /conf
      volumes:
        - name: config
          configMap:
            name: otel-collector-config
```

## Gotchas
- `memory_limiter` must be the first processor in every pipeline; placing it later means OOM can occur before it triggers.
- The Collector's own metrics are exposed on port 8888 (`/metrics`); scrape this to monitor pipeline health.
- `probabilistic_sampler` is stateless — the same trace ID may be kept on one node and dropped on another; use `tail_sampling` for consistent per-trace decisions.
- `contrib` image includes all receivers/exporters; it is larger than the core image — build a custom distribution with `ocb` for production.

## Related
- `prometheus-alertmanager-config.md`
- `log-aggregation-loki.md`
- `grafana-dashboard-as-code.md`
- `opentelemetry-2026-production.md`
