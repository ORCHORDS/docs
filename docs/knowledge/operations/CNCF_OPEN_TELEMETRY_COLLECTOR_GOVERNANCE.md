# CNCF OpenTelemetry Collector Governance

## Purpose

OpenTelemetry Collector (CNCF Incubating) is a vendor-neutral agent and gateway for receiving, processing, and exporting traces, metrics, and logs. The collector governance pattern captures the deployment topology (agent, gateway, sidecar), the receiver set (OTLP, Jaeger, Zipkin, Prometheus, Kafka), the processor pipeline (batch, memory_limiter, attributes, tail_sampling), the exporter configuration (Tempo, Jaeger, Prometheus, Loki, S3), and the documented pipeline order. Without explicit governance, collector configurations drift across deployments and break observability pipelines.

## Current context and source status

OpenTelemetry Collector v0.105 (released 2024) and v0.115 (released 2025) are the current supported versions. OpenTelemetry Collector 1.0 entered release candidate in 2026. The collector-distribution variants include `otelcol`, `otelcol-contrib`, and the AWS Distro for OpenTelemetry (ADOT). The project follows the CNCF Incubating governance model.

## Governance pattern

1. Pin the collector version and distribution variant in cluster bootstrap.
2. Deploy the collector as either a per-node agent (DaemonSet) or a per-cluster gateway (Deployment).
3. Define receivers explicitly (for example `otlp`, `prometheus`, `kafka`); disable unused receivers.
4. Define processors in a fixed pipeline order: `memory_limiter` first, then `batch`, then attribute enrichments, then `tail_sampling` (gateway only).
5. Define exporters with TLS and retry; route failures to the documented fallback.
6. Use `memory_limiter` with explicit `limit_mib` and `spike_limit_mib` to prevent OOM.
7. Use `batch` processor to amortize export costs.
8. Use `resourcedetection` to enrich spans with `service.name`, `service.namespace`, `deployment.environment`.
9. Monitor collector metrics: `otelcol_exporter_sent_spans`, `otelcol_exporter_send_failed_spans`, `otelcol_processor_batch_batch_send_size`.
10. Route pipeline failures to the on-call runbook with documented remediation.
11. Validate the collector config with `otelcol validate` before applying.

## Validation and evidence

- Collector version and distribution variant recorded in cluster inventory.
- Collector configuration committed to GitOps.
- `otelcol validate` exits 0 for the config file.
- Pipeline metrics deployed and reviewed.
- Synthetic telemetry confirms end-to-end pipeline delivery.

## Failure correction

Common defects include pipeline order violations (for example, `tail_sampling` before `batch`), missing `memory_limiter` causing OOM, and unbounded retries on a downstream outage. Corrective actions include enforcing pipeline order in CI validation, restoring `memory_limiter`, and configuring explicit retry limits and circuit breakers.

## Limitations

- Collector is not a tracing backend (use Jaeger or Tempo).
- Collector does not provide storage for spans (exporters required).
- `tail_sampling` requires load-balancing exporter with consistent trace ID routing.
- Some processor features are experimental; pin to stable processors for production.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (collector deployment topology), **engineering** (OpenTelemetry instrumentation), **reference** (OTLP specification), and **templates** (collector config template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- OpenTelemetry Collector documentation (CNCF Incubating): https://opentelemetry.io/docs/collector/
- OpenTelemetry Collector GitHub repository (CNCF Incubating): https://github.com/open-telemetry/opentelemetry-collector
- OpenTelemetry Protocol (OTLP) specification (CNCF Incubating): https://opentelemetry.io/docs/specs/otlp/

Sources were verified on September 1, 2026.