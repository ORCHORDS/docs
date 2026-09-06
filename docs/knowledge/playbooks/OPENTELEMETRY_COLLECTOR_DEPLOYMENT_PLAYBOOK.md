# OpenTelemetry Collector Deployment Playbook

## Purpose

Deploy the OpenTelemetry (OTel) Collector into a Kubernetes cluster or onto a host under the version, distribution, and semantic-convention constraints in `OPENTELEMETRY_VERSION_GOVERNANCE.md` without dropping telemetry or breaking downstream consumers.

## Audience

Platform engineers, observability engineers, SREs, and SDK owners integrating language instrumentation with the OTel Collector.

## Pre-conditions

- The destination is a supported Kubernetes release under `KUBERNETES_VERSION_GOVERNANCE.md` or a supported host OS.
- OTel Collector distribution is pinned to a supported minor under `OPENTELEMETRY_VERSION_GOVERNANCE.md`.
- The semantic conventions revision is pinned to the version declared by the running Collector.
- Downstream consumers (SIEM, metrics backend, traces backend, log backend) are reachable and have documented ingest schemas.

## Procedure

### Step 1 — Choose the distribution and deployment shape

1. Default to the OTel Collector `contrib` distribution for the receiver/feature set.
2. Default to the OTel Operator for Kubernetes deployments; deploy the Collector as a `Collector` custom resource.
3. For non-Kubernetes hosts, deploy the standalone Collector binary as a system service.

### Step 2 — Author the pipeline

4. Define receivers, processors, exporters, and extensions in the Collector configuration.
5. Pin every component to a version that ships in the running Collector distribution.
6. Validate the pipeline with the `otelcontribcol` binary in CI before deploying.

### Step 3 — Configure the receivers

7. Enable only the receivers required by the deployment; do not enable receivers that are not consumed downstream.
8. Configure TLS, authentication, and rate limits per the documented SDK expectations.
9. For Kubernetes, configure the kubeletstats and k8scluster receivers with the documented RBAC.

### Step 4 — Configure the processors and exporters

10. Configure batching, memory limiters, and resource detection processors per the documented SLO.
11. Configure exporters per the destination's documented ingest schema.
12. Configure a fallback exporter path in case the destination is unreachable.

### Step 5 — Stage and verify

13. Deploy the Collector in audit mode; emit telemetry to a test backend, not the production destination.
14. Verify the trace, metric, and log volume matches expectations.
15. Verify the destination's ingest schema accepts the payload without truncation or schema rejection.

### Step 6 — Promote to production

16. Switch the Collector to forward to the production destination.
17. Wire paging and on-call rotation for Collector health.
18. Capture a baseline of expected volume and time-to-process.

### Step 7 — Verify and operate

19. Confirm telemetry is flowing for every language SDK that integrates with the Collector.
20. Confirm semantic conventions match the documented revision.
21. Capture a recent pipeline health report and the most recent destination ingest log.

## Rollback

- Revert the Collector to the previous minor.
- Switch exporters back to the test backend.
- Capture a roll-forward plan for the next attempt and record the failure mode.

References: `OPENTELEMETRY_VERSION_GOVERNANCE.md`, `KUBERNETES_VERSION_GOVERNANCE.md`, `FALCO_RUNTIME_DETECTION_ROLLOUT_PLAYBOOK.md`.
