# CNCF Jaeger Tracing Sampled Governance

## Purpose

Jaeger (CNCF Graduated) is a distributed tracing platform originally developed at Uber and donated to CNCF. The sampled-tracing governance pattern captures the sampling decision (head-based, tail-based, adaptive), the sampling rate, the propagation format (W3C Trace Context `traceparent`, B3 `X-B3-*`), the storage backend (Elasticsearch, Cassandra, Kafka), and the retention policy. Without explicit governance, sampling decisions are made implicitly per service, which breaks trace correlation across services.

## Current context and source status

Jaeger 1.55 (released 2024) and Jaeger 1.60 (released 2025) are the current supported versions. Jaeger 2.0, which re-architects the storage and query layer, is in release candidate as of mid-2026. The project follows the CNCF Graduated governance model.

## Governance pattern

1. Adopt W3C Trace Context (`traceparent`, `tracestate`) as the primary propagation format; legacy B3 may be supported during transition.
2. Define a per-environment sampling rate (for example 100% for staging, 10% head-based for production).
3. Configure tail-based sampling for high-value operations (checkout, login, payment) at 100% capture.
4. Pin the collector, agent, query, and ingester versions in cluster bootstrap.
5. Record the storage backend, retention window (for example 7 days hot, 30 days cold), and indexing strategy.
6. Monitor Jaeger metrics: `jaeger_tracer_reporter_spans`, `jaeger_tracer_started_traces`, drop rate.
7. Alert on trace collection drop rate exceeding 5%.
8. Maintain a span attribute schema for cross-service correlation (`service.name`, `service.namespace`, `deployment.environment`).
9. Route trace sampling errors and backend failures to the on-call runbook.
10. Review sampling rates quarterly against storage cost and observability coverage.

## Validation and evidence

- Jaeger components and versions recorded in cluster inventory.
- Sampling rate configuration committed to GitOps.
- W3C Trace Context propagation verified by a synthetic test tracing across three services.
- Storage backend retention policy recorded in storage inventory.
- Prometheus metrics dashboard deployed and reviewed.
- Span attribute schema enforced by OpenTelemetry SDK collector configuration.

## Failure correction

Common defects include mixed propagation formats causing broken trace correlation, head-based sampling dropping high-value traces, and missing tail-based sampling on production-critical operations. Corrective actions include standardizing on W3C Trace Context, setting per-environment sampling rates, and routing checkout/login/payment through tail-based sampling at 100%.

## Limitations

- Jaeger does not generate metrics from spans (use OpenTelemetry Collector + Prometheus for metrics).
- Tail-based sampling requires Kafka or similar streaming backend.
- Sampling decisions are irrevocable at collection time; re-sampling requires re-instrumentation.
- Storage retention trade-offs affect cost and observability coverage.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (Jaeger deployment topology), **engineering** (OpenTelemetry instrumentation), **reference** (W3C Trace Context knowledge article), and **templates** (sampling rate template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- Jaeger documentation (CNCF Graduated): https://www.jaegertracing.io/docs/
- Jaeger GitHub repository (CNCF Graduated): https://github.com/jaegertracing/jaeger
- W3C Trace Context (W3C Recommendation, for propagation format): https://www.w3.org/TR/trace-context/

Sources were verified on September 1, 2026.