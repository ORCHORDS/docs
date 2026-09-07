# Jaeger Tracing Adoption Playbook

## Purpose
Provide a repeatable procedure for adopting Jaeger distributed tracing
in new or existing services so teams can deliver consistent trace
instrumentation, sampling policy, and pipeline integration.

## Audience
Service owners adopting Jaeger, platform engineers operating the
tracing backend, and reliability engineers integrating tracing into
incident response workflows.

## Pre-conditions
- Jaeger backend deployed and reachable from the target environment.
- OpenTelemetry SDK or Jaeger client libraries approved for the target
  language runtime.
- Service identity and authentication strategy decided for trace
  exporters.
- Capacity and retention targets agreed with the observability
  platform owner.
- Sampling policy and trace context propagation rules documented.

## Procedure
1. Confirm the Jaeger backend version is on the supported release line
   per the OpenTelemetry Collector Contrib governance card.
2. Add the tracing SDK dependency to the service and configure the
   OTLP exporter to forward spans to the agreed collector endpoint.
3. Instrument inbound and outbound HTTP, gRPC, messaging, and database
   calls so trace context propagates across process and service
   boundaries.
4. Apply the standard resource attributes so traces correlate with the
   same metadata captured for metrics and logs.
5. Configure head-based or tail-based sampling according to the
   service tier and traffic volume; record the chosen policy in the
   service handbook.
6. Validate end-to-end traces appear in Jaeger with consistent service
   names, operation names, and propagated baggage fields.
7. Wire trace identifiers into the incident response dashboards and
   on-call runbooks so responders can pivot from alerts to traces.
8. Document the rollout, owners, and known gaps in the service
   observability runbook before declaring adoption complete.

## Rollback
- Disable trace exporters in the service configuration so the runtime
  stops forwarding spans to the collector.
- Revert the SDK dependency to the prior pinned version if the
  instrumented build causes regression in latency or error rates.
- Drain in-flight spans and confirm the Jaeger backend reports no
  further trace data from the affected service.
- Capture the failure mode in the post-incident review and update
  this playbook with any newly identified guardrails.

## References
- [OpenTelemetry Collector Contrib governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)
- [Prometheus version governance](../reference/PROMETHEUS_VERSION_GOVERNANCE.md)
- [Jaeger version governance](../reference/JAEGER_VERSION_GOVERNANCE.md)
- [Service mesh mTLS rollout playbook](SERVICE_MESH_MTLS_ROLLOUT_PLAYBOOK.md)
