---
title: OpenTelemetry Collector Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://opentelemetry.io/docs/collector/ ; https://github.com/open-telemetry/opentelemetry-collector
---

# OpenTelemetry Collector Version Governance

## 1. Purpose

This reference card governs the lifecycle of the OpenTelemetry (OTel) Collector when deployed as the vendor-neutral telemetry pipeline for traces, metrics, and logs in ORCHORDS clusters and edge environments.

## 2. Scope

In scope:

- **otelcol** core binaries: `otelcol`, `otelcol-contrib`, `otelcol-k8s`.
- Distributions ≥ 0.110.x (current stable line) with collectors running the **Stable** API contract.
- Receivers (otlp, prometheus, jaeger, zipkin, k8scluster, kubeletstats, filelog, journald), processors (batch, memorylimiter, tail_sampling, transform, attributes, resource, filter), exporters (otlp, otlphttp, prometheusremotewrite, file, logging).
- Configuration loaded from a `ConfigMap`; secrets mounted via `env`/files.

Out of scope:

- Vendor-specific OTel SDKs in applications (handled in `engineering/observability/`).
- OpenTelemetry Operator CRD customisations outside the chart's documented values.

## 3. Versioning policy

- Pin the Collector binary to a specific patch release (e.g. `v0.110.0`) and SHA-256 digest.
- Keep receivers/exporters/processors together with the matching `go.opentelemetry.io/collector` version; mixing causes schema mismatch errors.
- Use the **k8s attributes processor** to inject `k8s.pod.uid`, `k8s.deployment.name`, etc. for resource attribution.
- Default to `memory_limiter` with `gc_interval=10s`, `spike_limit_percentage=20`, `check_interval=5s`.

## 4. Compatibility matrix

| otelcol-contrib | Receiver API | Exporter API | Notes |
| --- | --- | --- | --- |
| 0.105.x | v1 (stable) | v1 (stable) | filelog with checkpointing GA |
| 0.110.x | v1 | v1 | tail_sampling improved NUMA awareness |
| 0.115.x | v1 | v1 | Connector-based routing |

## 5. Pipeline topology

- **Agent**: per-node DaemonSet collecting host and pod metrics.
- **Gateway**: cluster-scoped deployment that aggregates, tails samples, and fans out to backends.
- Agent → Gateway → Backend (Jaeger, Prometheus remote-write, Loki, Tempo) is the canonical topology.

## 6. Data hygiene

- Scrub PII with the `transform` processor (`replace_pattern`) before exporting to long-term storage.
- Mask user data in span names and attribute keys via the `attributes` processor (`action: upsert` with `value: REDACTED`).
- Limit cardinality: set `memory_limiter` so a misbehaving metric cannot OOM the collector.

## 7. Upgrade procedure

1. Roll the Collector DaemonSet with the new image; tail the logs for `Component is not built...` warnings.
2. Validate pipelines with `otelcol validate --config=/etc/otel/config.yaml` before rollout.
3. Watch `otelcol_exporter_send_failed_<protocol>_spans/metrics/logs` and `otelcol_receiver_accepted_<metric>` for regressions.
4. Promote after 24 h green.

## 8. Rollback procedure

- `kubectl rollout undo daemonset/opentelemetry-collector-agent` reverts the image; the previous configuration persists until you re-apply the old ConfigMap.

## 9. Observability

- Required self-metrics: `otelcol_exporter_queue_size`, `otelcol_processors_batch_batch_send_size`, `otelcol_dropped_spans{reason}`, `otelcol_loadbalancer_num_backend_updates`.
- Alert on `otelcol_exporter_queue_size > 0.8 * capacity` and on `rate(otelcol_dropped_spans[5m]) > 0`.

## 10. References

- OTel Collector documentation — https://opentelemetry.io/docs/collector/
- OTel Collector configuration — https://opentelemetry.io/docs/collector/configuration/
