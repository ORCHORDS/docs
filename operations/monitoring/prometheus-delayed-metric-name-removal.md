# Prometheus delayed metric-name removal governance

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Delaying __name__ removal changes PromQL label semantics and can make expressions behave differently across feature-flag states.

## When to use

Use only to evaluate or adopt PromQL behavior that preserves metric names longer during expression evaluation.

## Controls

Pin Prometheus, gate the feature, run rule tests in both modes, and prohibit unreviewed semantic drift.

## Implementation

Inventory affected expressions, use promtool tests, canary one server, diff query results and alert states, then coordinate dashboards and recording rules.

## Tests

Test binary operations, functions, aggregations, duplicate-label errors, remote reads, rollback, and mixed-version replicas.

## Gotchas

Experimental behavior can change and must not be assumed portable across PromQL implementations.

## Official sources

- [Official documentation](https://prometheus.io/docs/prometheus/latest/feature_flags/)
