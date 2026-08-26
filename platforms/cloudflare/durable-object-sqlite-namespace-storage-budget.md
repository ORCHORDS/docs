# Durable Object SQLite namespace storage budget

**Issue:** Cloudflare's Total storage chart reports the hourly maximum for a SQLite-backed Durable Object namespace. It does not provide per-object storage and is absent for legacy KV-backed namespaces.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Budget namespace growth against workload units; inventory backend type; pair aggregate charts with application-owned coarse usage counters and deletion evidence; alert on slope and quota headroom.

## Verification

Insert, compact, delete, and restore representative data; verify hourly aggregation; reconcile sampled application totals; test cleanup without deleting legal holds.

## Gotchas

Aggregate storage cannot identify a leaking object. A falling chart is not proof that every deletion completed, and legacy namespaces need different evidence.

## Official sources

- https://developers.cloudflare.com/changelog/post/2026-07-20-durable-objects-total-storage-metrics/
- https://developers.cloudflare.com/durable-objects/observability/metrics-and-analytics/
