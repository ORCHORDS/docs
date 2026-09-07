# OpenTelemetry Collector Migration Playbook

## Purpose

Replace vendor-specific telemetry agents (Datadog, New Relic, Elastic APM, Splunk OTEL, etc.) with a unified OpenTelemetry Collector pipeline so that traces, metrics, and logs flow through a vendor-neutral, observable, and cost-controlled path.

## Audience

Platform engineers, SRE on-call, observability owners, application teams currently emitting telemetry to a vendor SDK.

## Pre-conditions

- OpenTelemetry Collector (otelcol-contrib) >= 0.110 deployed as a DaemonSet (agent) plus a cluster-scoped Deployment (gateway).
- A representative set of traces, metrics, and logs currently flowing to the incumbent vendor.
- A ConfigMap-based `config.yaml` committed in `gitops/otel/` with `memory_limiter`, `batch`, and `k8sattributes` processors enabled.
- Dashboards for `otelcol_exporter_queue_size`, `otelcol_dropped_spans`, and `otelcol_exporter_send_failed_*` already published.

## Procedure

1. **Inventory**: list every vendor SDK and agent currently in use. Record endpoints, authentication, sampling ratios, and cardinality.
2. **Shadow pipeline**: add an `otlp` exporter to the existing vendor pipeline so that a copy of traces/metrics/logs is also sent to the OTel Collector. Do not yet change application code.
3. **Validate parity**: for 7 days, compare vendor-side dashboards with the OTel-backed dashboards. Investigate any missing spans, dropped metrics, or cardinality explosions.
4. **Cut application SDKs**: switch each application from the vendor SDK to the OpenTelemetry SDK, keeping the same `service.name` and resource attributes. Keep vendor SDKs running in parallel until step 6.
5. **Tighten sampling**: apply `tail_sampling` at the gateway with a 10% default and 100% for error traces. Tune after observing cost and coverage.
6. **Disable vendor agents**: after 14 days of green parity, uninstall vendor agents and SDKs. Keep a 7-day rollback window by leaving the vendor exporter in the ConfigMap but commented out.
7. **Document**: update `policies/observability/pipeline.md` with the new topology, sampling policy, and cost attribution labels.

## Rollback

- Re-enable the vendor exporter in the Collector ConfigMap and re-deploy. No application code change is required if the OpenTelemetry SDK remains in place, because both backends can ingest OTLP.
- If an application SDK change is the root cause, revert the application to the previous vendor SDK and keep the Collector as a parallel path.

## References

- OpenTelemetry Collector documentation — https://opentelemetry.io/docs/collector/
- Internal: Batch 101 reference card `OPENTELEMETRY_COLLECTOR_VERSION_GOVERNANCE.md`.
