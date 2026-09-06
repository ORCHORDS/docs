---
title: OpenTelemetry Collector Version Governance (CNCF OpenTelemetry)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: OpenTelemetry project (https://opentelemetry.io/), CNCF Incubating; OpenTelemetry Collector v0.107 (May 2025), v0.108 (June 2025), v0.109 (July 2025), v0.110 (August 2025), v0.111 (October 2025), v0.112 (December 2025), v0.113 (February 2026), v0.114 (April 2026), v0.115 (June 2026), v0.116 (August 2026); distributions (core, contrib, k8s); semantic conventions; instrumentation SDKs
---

# OpenTelemetry Collector Version Governance (CNCF OpenTelemetry)

## Scope

This card governs how `orchords-docs` evaluates the OpenTelemetry (OTel) Collector and the surrounding ecosystem (OTel SDKs, instrumentation libraries, semantic conventions, exporters, receivers, processors, extensions, OTel Collector Contrib, OTel Operator). It is the reference input for any KB card that cites tracing, metrics, logs, or telemetry pipelines.

## Why this card exists

OpenTelemetry is the de-facto cross-language instrumentation and observability pipeline. The Collector ships roughly monthly minor releases; the SDKs follow a per-language cadence; semantic conventions evolve under a separate versioning scheme. A KB card that cites "OpenTelemetry" without binding to the Collector distribution, the language SDK version, and the semantic convention revision produces a pipeline that drifts the moment an exporter, a receiver, or a convention changes.

## Version support matrix (2026-09)

| Collector | Released | EoL | Notes |
|---|---|---|---|
| v0.113 | February 2026 | ~30 days after v0.114 | supported |
| v0.114 | April 2026 | ~30 days after v0.115 | supported |
| v0.115 | June 2026 | ~30 days after v0.116 | supported |
| v0.116 | August 2026 | current | latest |

Policy:

- Support the current minor and the previous minor (N-1).
- Upgrade window: ≤ 30 days after a new minor release.
- Pin the semantic conventions to the version declared by the running Collector; do not mix conventions from older Collectors.

## Distribution guidance

- Use the OTel Collector `contrib` distribution for the receiver/feature set; do not mix core and contrib in the same pipeline.
- The Kubernetes Operator for OTel (`opentelemetry-operator`) tracks the Collector minor and is the recommended way to deploy managed Collectors.

## Pipeline guidance

- Pin every receiver, processor, exporter, and extension to versions that ship in the running Collector distribution.
- Validate the pipeline with the `otelcontribcol` binary in CI before deploying.
- Treat semantic-convention upgrades as breaking changes; review and test exhaustively.

## SDK guidance

- Pin the language SDK to a version that declares compatibility with the running Collector minor and the running semantic conventions.
- Avoid mixing OTLP/HTTP and OTLP/gRPC in the same Collector without a documented reason.

References: `https://opentelemetry.io/`, `https://github.com/open-telemetry/opentelemetry-collector`, `https://github.com/open-telemetry/opentelemetry-collector-contrib`, `https://github.com/open-telemetry/opentelemetry-operator`, `https://opentelemetry.io/docs/specs/semconv/`.
