# OpenTelemetry batch metadata cardinality limit

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Batching by client metadata can create unbounded batchers and memory growth when metadata values have high cardinality.

## When to use

Use when an OpenTelemetry Collector batch processor intentionally separates telemetry by authenticated client metadata.

## Controls

Allowlist metadata keys, set metadata_cardinality_limit, bound queues and memory, and never use arbitrary headers as tenant identity.

## Implementation

Normalize trusted metadata before batching, configure the smallest key set and hard limit, expose processor metrics, and load-test eviction behavior.

## Tests

Test spoofed values, limit exhaustion, tenant bursts, retries, shutdown flush, config reload, and data separation.

## Gotchas

The limit bounds distinct combinations, not semantic tenant correctness; dropping or merging behavior must be observed.

## Official sources

- [Official documentation](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/batchprocessor)
