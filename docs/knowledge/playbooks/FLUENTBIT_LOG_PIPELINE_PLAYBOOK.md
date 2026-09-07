# Fluent Bit Log Pipeline Deployment Playbook

## Purpose
Deploy Fluent Bit as a Kubernetes DaemonSet for cluster-wide log collection. The pipeline parses container logs, enriches them with Kubernetes metadata, and routes records through multi-output sinks: Loki for primary observability, Splunk HEC for compliance retention, and S3 for cold storage with cost-aware sampling. This playbook standardizes deployment, tuning, validation, and handover to SRE operations.

## Audience
Platform engineers responsible for the Kubernetes platform, observability engineers maintaining the centralized logging stack, SRE on-call teams operating the dashboards and alerts, and application owners who consume structured logs for service debugging.

## Pre-conditions
- Kubernetes cluster (1.24 or later) with node-level access for the DaemonSet
- Helm 3 installed and the local kubeconfig pointing at the target context
- Network routes from every node to Loki, the Splunk HEC endpoint, and the destination S3 bucket
- Service account with RBAC for `namespaces`, `pods`, and `configmaps` read, plus a ClusterRole binding for metadata enrichment (see `docs/knowledge/runbooks/fluentbit-rbac.md:14`)
- Audit log destination pre-provisioned with the agreed retention policy
- Signed certificate bundle for TLS to all three backends
- Memory and CPU budget per node approved by the platform team (typical 64 MiB request, 256 MiB limit)

## Procedure
1. Install the Fluent Bit Helm chart with a values file aligned to the workload memory budget (see `docs/knowledge/playbooks/fluentbit-values.yaml:1`).
2. Configure inputs: `tail` plugin for `/var/log/containers/*.log`; enable the `systemd` input only on distros that use journald for host services.
3. Configure parsers: `containerd`, `json`, `cri`, and `logfmt`. Order parsers so JSON and CRI apply before the logfmt fallback parser (see `docs/knowledge/playbooks/fluentbit-parsers.conf:3`).
4. Configure filters: `kubernetes` for pod, namespace, and label enrichment; `modify` to inject `cluster`, `env`, and `service.name` resource attributes; `grep` to gate emission by `severity`; `lua` for custom field transformations scoped per tag (see `docs/knowledge/playbooks/fluentbit-filters.conf:12`).
5. Configure outputs: `loki` for primary observability with tenant id wiring; `splunk_hec` for compliance-tagged logs with index routing; `s3` for cold storage with cost-aware sampling on `total_log_size` (see `docs/knowledge/playbooks/fluentbit-outputs.conf:7`).
6. Tune `mem_buf_limit`, `storage.total_chunks_size`, and `storage.max_chunks_up` for backpressure, and confirm node memory headroom absorbs a 4x burst against average volume.
7. Configure TLS on every output, pin the CA bundle via Secret mount, and set `tls.verify` to `On` for Loki, Splunk, and S3 endpoints.
8. Validate tag routing with a synthetic log emit. Use `kubectl exec` against a sample pod, confirm parsed records land in Loki, Splunk, and S3 with the expected tags and labels.
9. Wire pipeline health to a metrics endpoint exposed to Prometheus. Enable the `metrics` exporter on port `2020`, scrape via ServiceMonitor, and alert on `fluentbit_output_errors_total` and `fluentbit_output_retried_total` (see `docs/knowledge/playbooks/fluentbit-servicemonitor.yaml:21`).
10. Document the pipeline in the runbook, attach the dashboards and alert rules, and hand over to SRE operations with on-call routing and known failure modes.

## Rollback
Drain the DaemonSet to stop new ingestion (set `updateStrategy` to `OnDelete` or `kubectl drain` each node), retain queued logs in memory and filesystem buffers until the successor pipeline is healthy, capture the last applied Helm values and Secrets, document the rollback window and downstream sink impact, then revert by re-applying the previous release with `helm rollback`.

## References
- Fluent Bit governance: [Fluent Bit Version Governance](../reference/FLUENTBIT_VERSION_GOVERNANCE.md)
- Loki governance: [Loki Version Governance](../reference/LOKI_VERSION_GOVERNANCE.md)
- OpenTelemetry Collector governance: [OpenTelemetry Collector Contrib Version Governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)
