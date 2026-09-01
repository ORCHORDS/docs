---
title: "Monitoring Knowledge"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-02"
review-cycle: "90 days"
next-review: "2026-12-01"
---

# Monitoring Knowledge

Reusable operational guidance for OpenTelemetry, Prometheus, Mimir, Loki, Tempo, Pyroscope, Alertmanager, OTLP, Grafana, synthetic probes, SLO burn-rate alerting, and adjacent observability concerns.

## Selected guidance

### OpenTelemetry

- [OpenTelemetry Metric Temporality Selection](otel-metric-temporality-selection.md)
- [OpenTelemetry Exponential Histograms Adoption](otel-exponential-histograms-adoption.md)
- [OpenTelemetry Collector Pipeline Reliability](otel-collector-pipeline-reliability.md)
- [OTLP HTTP Versus gRPC Export Selection](otlp-http-vs-grpc-export.md)

### Prometheus stack

- [Prometheus Native Histograms Rollout](prometheus-native-histograms-rollout.md)
- [Prometheus Remote Write Tuning](prometheus-remote-write-tuning.md)
- [Prometheus Scrape ODR Reduction](prometheus-scrape-odr-reduction.md)
- [Mimir Blocks Storage and Retention](mimir-blocks-storage-retention.md)
- [Alertmanager Route and Silence Union Semantics](alertmanager-route-silence-union.md)

### Logs, traces, profiles

- [Loki Label Cardinality Control](loki-label-cardinality-control.md)
- [Loki Structured Metadata and Patterns](loki-structured-metadata-patterns.md)
- [Tempo Trace ID Linkage and Service Graph](tempo-trace-id-linkage-service-graph.md)
- [Pyroscope eBPF Profile Cardinality Governance](pyroscope-ebpf-profile-cardinality.md)

### SLO and synthetic

- [Grafana Dashboard-as-Code Folder Permissions](grafana-dashboard-as-code-folders.md)
- [Synthetic Probe Geographic Distribution](synthetic-probe-geo-distribution.md)
- [SLO Burn-Rate Alert Window Pairs](slo-burn-rate-alert-windows.md)
- [Histogram Bucket Boundary Selection](histogram-bucket-boundary-selection.md)
