# Service Mesh Observability

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Kubernetes services communicate via plain HTTP/gRPC. You have no
visibility into inter-service traffic: which service calls which, what the
latency between hops is, whether mTLS is enforced, or where failures
originate in a multi-hop request chain. Distributed tracing is manual and
incomplete.

## Context

A service mesh provides a dedicated infrastructure layer for service-to-
service communication, handling mTLS, traffic management, and observability
transparently. In 2026, the three dominant service meshes are Istio (ambient
mode), Linkerd, and Cilium Service Mesh. Each provides automatic telemetry
— metrics, traces, and access logs — without application code changes.

## Observability by mesh

### Istio (Ambient Mode — recommended for new clusters in 2026)

Istio's ambient mode replaces per-pod sidecar proxies with a per-node
ztunnel (L4) and optional waypoint proxies (L7), reducing memory usage by
50-70% versus sidecar Istio.

- **Metrics:** Envoy emits hundreds of metrics per service. Key ones:
  `istio_request_duration_milliseconds`, `istio_requests_total`,
  `istio_tcp_connections_opened_total`. Integrates with Prometheus natively.
- **Tracing:** automatic span injection for HTTP/gRPC. Integrates with
  Jaeger, Zipkin, and OTel Collector. Requires header propagation
  (B3/W3C Trace Context) in application code.
- **Topology:** Kiali provides real-time service dependency graphs,
  traffic flow visualization, and health indicators.
- **Caveat:** Envoy's metric cardinality is high. Use Prometheus recording
  rules to pre-aggregate, or enable Istio's metric merging.

### Linkerd

Linkerd focuses on simplicity and the golden signals. Its Linkerd Viz
extension provides a clean CLI and dashboard out of the box.

- **Metrics:** focused on golden signals — success rate, request rate,
  latency percentiles per route. Lower cardinality than Istio.
- **Tracing:** distributed tracing via OpenTelemetry integration.
  Requires the `linkerd-jaeger` extension.
- **Topology:** `linkerd viz dashboard` shows real-time service topology,
  per-route metrics, and live traffic.
- **Caveat:** Linkerd's company (Buoyant) changed to a non-open-source
  license for stable releases in 2024. Evaluate licensing before adoption.

### Cilium Service Mesh

Cilium uses eBPF to implement mesh functionality directly in the Linux
kernel, avoiding per-pod proxy overhead entirely.

- **Metrics:** Hubble provides eBPF-powered network and application
  observability. Visibility into DNS, HTTP, gRPC, and Kafka traffic at the
  kernel level with minimal overhead. Standard Prometheus metrics export.
- **Tracing:** Hubble integrates with Jaeger and OTel for distributed
  tracing. eBPF traces at the kernel level without requiring application-
  side header propagation for L3/L4 visibility.
- **Topology:** Hubble UI provides network flow visualization, service
  maps, and DNS query monitoring.
- **Caveat:** L7 policy enforcement (HTTP routing, retries) requires
  Envoy proxy injection, partially negating the "no proxy" advantage.

## Comparison

| Capability | Istio Ambient | Linkerd | Cilium |
|---|---|---|---|
| Proxy model | ztunnel (L4) + waypoint (L7) | Per-pod sidecar (Rust) | eBPF (L3/L4) + Envoy (L7) |
| Memory overhead | Medium (50-70% less than sidecar) | Low (Rust proxy) | Lowest (eBPF) |
| Metric cardinality | High (Envoy) | Low (golden signals) | Medium (Hubble) |
| Topology visualization | Kiali | Linkerd Viz | Hubble UI |
| Tracing | Jaeger/Zipkin/OTel | OTel (via extension) | Hubble + Jaeger |
| Best for | Full L7 features | Simplicity, low overhead | Performance, eBPF |

## Integration with OpenTelemetry

All three meshes export metrics to Prometheus and traces to OTel Collector.
The recommended 2026 pattern:

1. Mesh exports Prometheus metrics → OTel Collector scrapes.
2. Mesh injects trace headers → OTel Collector receives spans.
3. OTel Collector exports to your observability backend (Grafana Cloud,
   Datadog, Honeycomb).

## Anti-patterns

- **Deploying a mesh for observability alone** — if you only need metrics
  and traces, OTel auto-instrumentation is lighter. Deploy a mesh when you
  also need mTLS, traffic management, or policy enforcement.
- **Ignoring metric cardinality** — Istio's Envoy can generate millions of
  time series in a large cluster. Configure metric filtering or use
  recording rules from day one.
- **Relying on mesh tracing without header propagation** — meshes inject
  spans but cannot correlate them across services without trace context
  propagation (W3C Trace Context or B3). Your app must forward headers.

## Gotchas

- **Ambient mode is still evolving** — Istio ambient reached GA but some
  L7 features require waypoint proxy deployment. Not all Istio features
  are available without sidecars.
- **Linkerd license change** — Buoyant moved stable Linkerd releases to a
  non-OSS license. Edge releases remain Apache 2.0 but are not
  recommended for production.
- **Cilium eBPF kernel requirements** — requires Linux kernel 5.10+ (ideally
  5.15+). Older kernels lack required eBPF features.
- **Mesh-to-mesh migration is painful** — CRDs, policies, and mTLS
  certificates are mesh-specific. Plan for a parallel-run migration, not a
  big-bang cutover.

## Verification

- Verify mTLS is enforced between all services (`istio-proxy` access logs,
  `linkerd viz edges`, or Hubble flows show `encrypted=true`).
- Confirm golden signal dashboards show data for all services in the mesh.
- Trace a request end-to-end through multiple services and verify all hops
  appear in the trace.
- Load test and verify mesh overhead stays within budget (< 1ms added p50
  latency per hop for Cilium, < 2ms for Istio ambient, < 1.5ms for Linkerd).

## Related

- `documentation/categories/monitoring/opentelemetry-overview.md`
- `documentation/categories/monitoring/prometheus-setup-basics.md`
- `documentation/categories/monitoring/golden-signals-monitoring.md`
- `documentation/categories/security/spiffe-workload-identity-and-short-lived-mtls.md`

## Source URLs (verified 2026-08-16)

- Kubernetes service mesh comparison 2026: Istio vs Linkerd vs Cilium — https://reintech.io/blog/kubernetes-service-mesh-comparison-2026-istio-linkerd-cilium
- Cilium vs Istio service mesh comparison 2026 — https://lucaberton.com/blog/service-mesh-istio-ambient-cilium/
- Service mesh 2026: Cilium wins — https://algeriatech.news/service-mesh-cilium-consolidation-2026/
- Service mesh Istio Linkerd and beyond 2026 — https://calmops.com/software-engineering/service-mesh-istio-linkerd-kubernetes/
