---
title: "Jaeger Distributed Tracing Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "Jaeger project release notes and CNCF Jaeger observability community guidance"
---

# Jaeger Distributed Tracing Version Governance

## Platform Overview

Jaeger is a CNCF-graduated distributed tracing platform designed for microservice observability. It provides end-to-end transaction visibility, dependency graph reconstruction, and root cause analysis across polyglot service fleets. The current stable line is the Jaeger 1.x series, governed under CNCF with releases coordinated through the Jaeger release cadence.

## Architecture

A production Jaeger deployment comprises five components. The `jaeger-agent` runs as a sidecar or host daemon and batches spans locally. The `jaeger-collector` validates, indexes, and writes spans to a configured backend. `jaeger-query` serves the UI and HTTP/gRPC API for trace retrieval. `jaeger-ingester` reads from Kafka and forwards to the collector, enabling async pipelines. `jaeger-all-in-one` combines agent, collector, and query for development and evaluation only.

## Storage Backends

Supported backends include Cassandra, Elasticsearch, OpenSearch, and Kafka (used with the ingester for buffering). A gRPC storage plugin interface enables custom and third-party backends, including the OpenSearch-native plugin introduced in the 1.x line. Selection depends on scale, indexing needs, and operational familiarity.

## Trace Data Model

Jaeger models traces as directed acyclic graphs of spans. Each span carries a span context (trace ID, span ID, parent ID, sampling flags, baggage) propagated across process boundaries via W3C Trace Context or the legacy Jaeger propagation format. Baggage provides cross-process key-value propagation for user-defined context.

## Sampling Strategies

Jaeger supports probabilistic sampling, rate limiting, remote sampling coordinated through the collector, adaptive sampling driven by observed load, and tail-based sampling for post-hoc decisions. Remote sampling is the recommended default for production fleets.

## Client Libraries and Protocols

Officially maintained clients include `jaeger-client-go`, `jaeger-client-node`, `jaeger-client-python`, and `jaeger-client-java`. Jaeger accepts spans over OTLP (the strategic protocol) and the legacy Jaeger Thrift protocol over UDP and HTTP. Jaeger Thrift receivers are slated for deprecation; OTLP is the supported intake path going forward.

## Compatibility Horizon

Jaeger 1.x is the supported line. The project tracks OpenTelemetry SDK and Collector releases for ingestion compatibility. OpenTelemetry Collector and SDKs can emit directly to Jaeger via OTLP without the legacy Thrift path.

## Version Selection Decision Tree

1. **Storage backend** - select Elasticsearch or OpenSearch for indexed query workloads; Cassandra for write-heavy scale; Kafka with a downstream sink for buffering.
2. **Sampling strategy** - default to remote adaptive sampling for production; use probabilistic or rate limiting for low-volume or test workloads.
3. **Topology** - choose `jaeger-all-in-one` only for development; deploy agent, collector, query, and ingester as separate services in production.
4. **Protocol** - prefer OTLP for new instrumentation; restrict Jaeger Thrift to legacy migration windows.

## Operational Impact

Thrift deprecation reduces long-term protocol surface. OTLP adoption requires coordinating SDK upgrades across languages and ensuring the collector tier accepts gRPC. Storage migrations between backends are non-trivial and require dual-write validation windows.

## Cross-References

See [OpenTelemetry Collector Contrib version governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md) for the upstream collector governance card.
See [Prometheus version governance](PROMETHEUS_VERSION_GOVERNANCE.md) for metrics pipeline integration.
See [Google SRE release engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md) for release-engineering practice context.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.