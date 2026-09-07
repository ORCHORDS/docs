---
title: OpenTelemetry Collector Contrib Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/open-telemetry/opentelemetry-collector-contrib
---

# OpenTelemetry Collector Contrib Version Governance

## Purpose
Define how teams select, upgrade, and operate OpenTelemetry Collector
Contrib distributions so telemetry pipelines stay supported, secure, and
interoperable with downstream observability backends.

## Scope
Applies to the upstream `opentelemetry-collector-contrib` distribution
and any internal forks packaged as container images, sidecars, or
daemonset agents across development, staging, and production
environments.

## Version Line Policy
- Track the latest stable minor release for at least 90 days before
  declaring a new line production-ready.
- Hold one previous minor release for rollback for at least 30 days
  after promotion.
- Skip releases flagged by upstream as containing breaking receiver or
  exporter schema changes without an internal exception record.
- Align collector binary version with the OpenTelemetry SDK version
  shipped in application runtimes.

## Component Lifecycle
- Receivers, processors, and exporters move between `alpha`, `beta`, and
  `stable` per the upstream stability ladder.
- Components in `alpha` are not permitted in production pipelines
  without an architecture-review exception.
- Components in `beta` may be used in production with documented
  mitigation and rollback owners.
- Deprecated components must be replaced within two minor release
  cycles; pipelines failing to migrate generate a non-compliance
  finding.

## Compatibility Considerations
- Wire protocol compatibility is required against the configured
  OpenTelemetry Protocol (OTLP) endpoints, including gRPC and HTTP
  variants.
- Resource attribute semantics must align with the semantic conventions
  adopted by downstream storage backends.
- TLS, mTLS, and authentication configuration must interoperate with
  the platform identity provider used for service-to-service trust.
- Logging exporter payloads must be parseable by the central log
  indexing stack without format conversion adapters.

## Upgrade Procedure
1. Read upstream release notes and identify breaking changes affecting
   enabled receivers, processors, or exporters.
2. Update the staging collector configuration with the new version and
   validate against synthetic traffic mirroring production shape.
3. Run the canary pipeline for 24 hours and confirm metrics, traces,
   and logs reach the destination backends with no data loss.
4. Promote the new version through production waves with defined
   rollback owners and pre-staged previous-version artifacts.
5. Record the upgrade window, observed deltas, and any compensating
   configuration changes in the change log.

## Rollback Procedure
- Re-deploy the previous collector image and configuration from the
  versioned artifact store.
- Disable any receivers, processors, or exporters newly introduced in
  the rolled-back version.
- Re-validate telemetry delivery against the synthetic probes and
  confirm queue and retry behaviour returns to the prior baseline.
- Open a regression ticket capturing the cause of the rollback and link
  it to the originating upgrade record.

## Security Considerations
- Pin collector images by digest and verify signatures using the
  container trust store.
- Restrict network egress so collectors only forward to approved
  observability endpoints.
- Scrub sensitive resource attributes using the configured
  `attributes/` processor before export.
- Rotate any credentials embedded in exporter configuration when
  collector instances are reprovisioned.

## Operational Impact Points
- Collector upgrades require coordinated restarts; expect momentary
  telemetry drops covered by exporter retry on queue.
- Large `batch` processor settings trade memory for throughput;
  validate against expected peak load.
- Persistent queues trade disk usage for durability across collector
  restarts.
- Custom receivers and exporters written in-house must be tracked in
  the internal components registry and re-evaluated per release.

## Cross-References
- See [Prometheus version governance](PROMETHEUS_VERSION_GOVERNANCE.md).
- See [Jaeger version governance](JAEGER_VERSION_GOVERNANCE.md).
- See [Google SRE release engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md).

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
