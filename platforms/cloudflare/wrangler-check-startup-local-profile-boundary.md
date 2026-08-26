# Wrangler check startup local-profile boundary

**Issue:** Wrangler 4.116+ reports bundle sizes and local startup CPU profile, but local duration is not production startup time.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Pin Wrangler, baseline raw/gzip size and sampled work, archive cpuprofile safely, verify authoritative deployed startup separately.

## Tests

Dependency regression, source maps, platform CPU difference, reproducible rerun.

## Gotchas

A local flamegraph locates work but cannot certify edge latency.

## Official sources

- https://developers.cloudflare.com/changelog/
