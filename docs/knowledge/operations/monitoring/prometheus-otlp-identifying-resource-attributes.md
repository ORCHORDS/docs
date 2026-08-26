# Prometheus OTLP identifying-resource attributes

**Problem**

Promoting resource attributes into target identity can merge or fragment telemetry unexpectedly.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when OTLP resource identity must remain queryable in Prometheus.

## Controls

- Configure identifying attributes explicitly.
- Allowlist stable low-cardinality fields.
- Coordinate queries, remote write, and retention.

## Implementation

Canary one resource class, detect collisions/churn, and version semantic mappings.

## Tests

Send missing, conflicting, changing, and high-cardinality attributes; compare series and staleness.

## Gotchas

- Identity changes create new series.
- Labels can collide.
- More labels increase cost.

## Official sources

- [Prometheus OTLP configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#otlp)
