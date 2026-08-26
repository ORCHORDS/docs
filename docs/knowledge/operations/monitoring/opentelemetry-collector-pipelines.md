# OpenTelemetry Collector Pipeline Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your observability stack is a tangle of vendor-specific agents — a
Datadog agent for metrics, a Jaeger agent for traces, a Fluentd
instance for logs — each with its own configuration, resource footprint,
and upgrade cycle. Adding a new observability backend requires deploying
another agent. You cannot filter, transform, or route telemetry data
before it reaches the backend, leading to high ingestion costs from
noisy, unprocessed data.

## Context

The OpenTelemetry Collector is a vendor-agnostic proxy that receives,
processes, and exports telemetry data (traces, metrics, logs). It
replaces multiple vendor-specific agents with a single configurable
pipeline. In 2026, the Collector is the de facto standard for telemetry
routing — supported by every major observability vendor (Datadog,
Grafana, New Relic, Honeycomb, Splunk) as an ingestion path. The
Collector's pipeline architecture (receivers → processors → exporters)
enables cost optimization through filtering and sampling before data
reaches expensive backends.

## Pipeline architecture

```
┌──────────┐     ┌────────────┐     ┌──────────┐
│ Receivers│────►│ Processors │────►│ Exporters│
└──────────┘     └────────────┘     └──────────┘
  OTLP            batch              OTLP
  Jaeger          memory_limiter     Prometheus
  Prometheus      filter             Jaeger
  Zipkin          attributes         Datadog
  filelog          tail_sampling      Loki
  hostmetrics     transform          S3
```

### Configuration structure

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    send_batch_size: 1024
    timeout: 5s
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128

exporters:
  otlphttp:
    endpoint: https://otel-backend.example.com:4318

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp]
```

## Deployment patterns

### Agent (DaemonSet)

Deploy a Collector instance on every node. Applications send telemetry
to the local Collector via localhost, minimizing network latency and
providing node-level resource metrics.

```yaml
# Kubernetes DaemonSet
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-collector-agent
spec:
  template:
    spec:
      containers:
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:latest
          ports:
            - containerPort: 4317  # OTLP gRPC
            - containerPort: 4318  # OTLP HTTP
```

### Gateway (Deployment)

A centralized Collector service that receives telemetry from agents or
directly from applications. Handles heavy processing (sampling,
enrichment, routing) in one place.

```
Applications → Agent Collectors (DaemonSet) → Gateway Collector (Deployment) → Backends
```

### Combined (Agent + Gateway)

Most production deployments use both:
- **Agent**: lightweight, handles receiving and basic batching
- **Gateway**: handles filtering, sampling, transformation, and
  multi-backend routing

## Key processors

### Filtering (cost reduction)

```yaml
processors:
  filter:
    traces:
      span:
        - 'attributes["http.target"] == "/health"'
        - 'attributes["http.target"] == "/ready"'
    metrics:
      metric:
        - 'name == "system.cpu.time" and resource.attributes["host.name"] == "debug-host"'
```

### Tail sampling (traces)

```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: errors-always
        type: status_code
        status_code: { status_codes: [ERROR] }
      - name: slow-traces
        type: latency
        latency: { threshold_ms: 1000 }
      - name: sample-rest
        type: probabilistic
        probabilistic: { sampling_percentage: 10 }
```

Tail sampling examines the complete trace before deciding whether to
keep or drop it. This ensures all error traces and slow traces are
retained while sampling routine traces.

### Attribute transformation

```yaml
processors:
  attributes:
    actions:
      - key: db.password
        action: delete
      - key: environment
        value: production
        action: upsert
  transform:
    trace_statements:
      - context: span
        statements:
          - truncate_all(attributes, 256)
```

## Multi-backend routing

Route different telemetry types or priorities to different backends:

```yaml
exporters:
  otlphttp/primary:
    endpoint: https://primary-backend.example.com
  otlphttp/archive:
    endpoint: https://s3-archive.example.com
  otlphttp/errors:
    endpoint: https://error-tracking.example.com

connectors:
  routing:
    table:
      - statement: route() where attributes["error"] == true
        pipelines: [traces/errors]
      - statement: route()
        pipelines: [traces/archive]

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/primary]
    traces/errors:
      receivers: [routing]
      exporters: [otlphttp/errors]
    traces/archive:
      receivers: [routing]
      exporters: [otlphttp/archive]
```

## Anti-patterns

- **No memory limiter** — the Collector can consume unbounded memory
  under high load, causing OOM kills. Always include the
  `memory_limiter` processor as the first processor in every pipeline.
- **Sampling at the agent** — head sampling at the agent drops spans
  that might be part of an error trace. Use tail sampling at the
  gateway where complete traces are visible.
- **Single Collector for everything** — a single Collector handling
  receive, process, and export for all telemetry becomes a bottleneck.
  Use agent + gateway separation for production workloads.
- **Exporting everything unfiltered** — sending all telemetry to an
  expensive backend without filtering health checks, debug spans, and
  noisy metrics. Filter before exporting to control costs.

## Gotchas

- **Contrib vs. core distribution** — the core Collector includes
  minimal receivers/exporters. The `contrib` distribution includes
  vendor-specific components (Datadog, Loki, Kafka exporters). Use
  contrib or build a custom Collector with only the components you need.
- **Tail sampling requires a gateway** — tail sampling needs to see all
  spans of a trace in one Collector instance. With agent-only deployment,
  spans from different services land on different agents. Route all
  traces to a gateway for tail sampling.
- **Configuration hot reload** — the Collector supports config reload
  via SIGHUP, but not all changes are safe to reload (receiver endpoint
  changes require a restart).
- **Resource attribution** — Kubernetes metadata (pod name, namespace,
  node) is added by the `k8sattributes` processor, which requires RBAC
  permissions to query the K8s API.

## Verification

- Memory limiter is the first processor in every pipeline.
- Health check and readiness endpoints are filtered before export.
- Tail sampling retains 100% of error and slow traces.
- Telemetry ingestion cost is tracked and attributed per service.
- Agent + gateway deployment pattern is used for production.
- Collector resource usage (CPU, memory) is monitored and alerted.

## Related

- `documentation/docs/policies/monitoring/frontend-real-user-monitoring-rum.md`
- `documentation/docs/policies/monitoring/synthetic-monitoring-uptime-checks.md`
- `documentation/docs/policies/infra/observability-stack.md`

## Source URLs (verified 2026-08-16)

- OpenTelemetry Collector docs — https://opentelemetry.io/docs/collector/
- Collector configuration guide — https://opentelemetry.io/docs/collector/configuration/
- Collector deployment patterns — https://medium.com/@alokrahuldevops/day-167-opentelemetry-collector-deployment-modes-and-patterns-d4205622eb05
- Advanced pipeline routing — https://oneuptime.com/blog/post/2026-02-09-otel-collector-pipelines-routing/view
