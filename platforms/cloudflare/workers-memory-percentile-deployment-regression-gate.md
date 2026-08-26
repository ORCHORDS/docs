# Workers memory-percentile deployment regression gate

**Issue:** Workers and Durable Objects now expose invocation memory percentiles (P50 through P999) with deployment markers. Use them as regression evidence, not as per-request heap profiles.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Set a service-specific baseline and alert on sustained upper-percentile movement; correlate by deployed version; persist important Durable Object state because in-memory state disappears on eviction; control label cardinality.

## Verification

Replay representative concurrency and object populations; deploy a known memory increase; verify alert, version correlation, rollback, and post-eviction correctness.

## Gotchas

The metric samples isolate memory and one isolate can serve concurrent requests. A percentile is not a heap attribution, and local CPU/memory profiles are not production measurements.

## Official sources

- https://developers.cloudflare.com/changelog/product/workers/
- https://developers.cloudflare.com/workers/observability/metrics-and-analytics/
