---
title: "Fluent Bit Log Processor Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "Fluent Bit project release notes and CNCF Fluent community guidance"
---

# Fluent Bit Log Processor Version Governance

## Overview

Fluent Bit is a CNCF graduated, lightweight log processor and forwarder designed for high-throughput, resource-constrained environments. It is written in C and engineered for edge, container, and centralized aggregation workloads.

## Input Plugins

Standard inputs include `tail` (file following with offset tracking), `systemd` (journal ingestion), `forward` (Fluent protocol receiver), `tcp`, `udp`, and `http` (line-oriented receivers), `prometheus_scrape` (metrics scraping), `fluentbit_metrics` (self-observability), `exec` (external command output), and `winlog` (Windows Event Log).

## Parser Formats

Supported parsers cover `json`, `regex`, `ltsv`, `logfmt`, `apache`, and `nginx`, configured via `parsers.conf`.

## Filter Plugins

Available filters include `grep` (record matching), `kubernetes` (metadata enrichment), `modify` (record mutation), `rewrite_tag` (dynamic routing), `throttle` (rate control), `nest` (payload flattening or embedding), `lua` (scripted processing), and `geoip` (geolocation enrichment).

## Output Plugins

Outputs include `forward` (Fluent protocol), `kafka`, `http`, `es`, `opensearch`, `splunk`, `prometheus`, `prometheus_exporter`, `loki`, `file`, `stdout`, and `s3`.

## Streaming Engine

Fluent Bit's streaming engine is a C-native pipeline with explicit backpressure controls, allowing predictable memory ceilings and bounded queue depth under load spikes.

## Configuration Model

Configuration uses `@SET` directives, `@INCLUDE` for modular files, `parsers.conf` for parser definitions, and WASM-based custom plugins for extensible processing without recompilation.

## Deployment Patterns

Common patterns include sidecar (per-pod co-location), DaemonSet (per-node agent), and dedicated aggregator (tiered fan-in).

## Compatibility Horizon

The Fluent Bit 3.x line is the active support branch. New deployments should adopt 3.x; existing 2.x deployments should plan migration before upstream support concludes.

## Version Selection Decision Tree

Evaluate in order:

1. Deployment mode (sidecar, DaemonSet, aggregator) - determines resource ceiling.
2. Parser choice - confirm the required format is supported in the target minor version.
3. Output backend set - verify all sinks are released and stable in the target build.
4. Memory budget - select a build with or without debug features accordingly.
5. WASM plugin usage - require 3.x or later for stable WASI support.

## Operational Impact

- Pin minor versions in manifests to ensure reproducible builds.
- Track CNCF release notes for deprecations before each upgrade.
- Validate parser and output plugin compatibility against the target Fluent Bit minor version.
- Review chunk limits, flush intervals, and retry policies per workload.
- Verify WASM plugins against the target runtime before rollout.

## Cross-references

- See input plugin reference at `docs/knowledge/reference/fluentbit-input-plugins.md:12`.
- See output plugin reference at `docs/knowledge/reference/fluentbit-output-plugins.md:18`.
- See deployment guidance at `docs/knowledge/reference/fluentbit-deployment-patterns.md:7`.
- See parser reference at `docs/knowledge/reference/fluentbit-parsers.md:5`.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
