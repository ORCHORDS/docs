# OpenTelemetry Collector Deployment Adoption Playbook

## Purpose
This runbook guides platform teams through deploying OpenTelemetry (OTel) Collector in agent and gateway topologies. It covers wiring receivers, processors, exporters, and tail-based sampling, and integrating telemetry with backends such as Jaeger, Tempo, Loki, and Prometheus. The goal is a reproducible, auditable rollout that bounds resource use, controls metric cardinality, and converges signals into a small set of trusted backends.

## Audience
Platform engineers, SREs, observability engineers, and application owners responsible for cluster telemetry. Assumes working familiarity with Kubernetes, Helm, and at least one traces or metrics backend.

## Pre-conditions
- Kubernetes cluster (1.24 or newer) with admin context for the target namespace.
- Helm 3.10 or newer and a values repository under version control.
- Backend endpoints reachable from the cluster: Jaeger OTLP, Tempo OTLP/gRPC, Loki HTTP, Prometheus remote_write or scrape.
- Service identity for Workload Identity or projected ServiceAccount tokens.
- TLS certificates (root CA, server, client) plus a KMS or external secret store reference.
- Audit log destination (Loki or object storage) for collector self-telemetry.
- Capacity budget documented for CPU, memory, and persistent volume claims.

## Procedure
1. Choose deployment topology. Use agent (DaemonSet) when each node must emit locally with low egress and quick failure isolation. Use gateway (Deployment) when central enrichment, tail sampling, or cross-cluster fan-in is required. Many environments run both tiers.
2. Select the distribution. Default to `opentelemetry-collector` for stable core components. Select the Contrib distribution when extended receivers, processors, or exporters (Kafka, multiple backends, niche protocols) are required.
3. Render a Helm values file under the version-controlled values repository. Pin the image tag, resource requests and limits, priorityClassName, and podSecurityContext. Reference `values/agent.yaml` and `values/gateway.yaml` placeholders.
4. Define receivers per pipeline: `otlp` for in-cluster services, `jaeger` for legacy thrift traffic, `prometheus` for scrape workloads, `kafka` for asynchronous ingest, and `zipkin` for legacy spans.
5. Configure processors in the correct order: `memory_limiter` first, then `k8sattributes`, `transform` or `attributes`, `batch`, and finally `tail_sampling` (gateway only). Set `memory_limiter.limit_mib` below the pod memory limit to leave headroom for OOM scenarios.
6. Configure exporters per backend. Use `otlp` for Tempo and Jaeger, `otlp/jaeger` only when Jaeger lacks native OTLP, `prometheus` for remote_write, and `kafka` for downstream fan-out. Enable `retry_on_failure` and `sending_queue` on every exporter.
7. Wire extensions: `health_check`, `pprof`, `zpages`, and one authenticator (`sigv4auth` for AWS, `bearertokenauth` for general HTTP). Mount signing material via projected volumes.
8. Enable remote sampling. Load sampling policies from a central source (file_storage or remote URL) and refresh on a schedule. Start with a latency policy plus an error-rate policy before adding per-tenant rules.
9. Configure persistent volumes for `file_storage` extensions when the gateway must survive restart with retained trace data or queued exports. Size volumes from expected worst-case backlog.
10. Add a canary workload emitting OTLP traffic and verify spans in Jaeger or Tempo. Confirm trace IDs, service name, and resource attributes traverse every processor stage.
11. Validate the Prometheus scrape endpoint and inspect metric cardinality. Drop high-cardinality labels in the `transform` processor before they reach the exporter.
12. Hand over to SRE operations. Publish runbook links, alert routes, dashboards, and ownership contacts, then tag the release in the values repository.

## Rollback
Drain the agent DaemonSet with `kubectl rollout` and cordon affected nodes. Drain the gateway Deployment and scale it to zero only after exporters have flushed their queues. Retain pipeline state, file_storage volumes, and a final log snapshot for forensics. Document the rollback with timestamps, the git SHA of the previous values, and impacted service cohorts. Open a post-incident record and link it from the release tag.

## References
- [OpenTelemetry Collector Contrib Version Governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)
- [Jaeger Version Governance](../reference/JAEGER_VERSION_GOVERNANCE.md)
- [Fluent Bit Version Governance](../reference/FLUENTBIT_VERSION_GOVERNANCE.md)
