# Prometheus remote-write compression contract

**Problem**

Compression reduces network bytes but adds CPU and requires receiver compatibility; changing it can shift bottlenecks rather than improve throughput.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when remote-write network cost is material and both endpoints support the selected protocol behavior.

## Controls

- Keep the remote-write protocol and compression behavior compatible with the receiver.
- Measure sender CPU, bytes, queue lag, and receiver decode failures.
- Canary per endpoint.

## Implementation

- Change only one endpoint at a time and retain rollback.
- Keep required metadata and samples unchanged.
- Alert on retries and dropped samples.

## Tests

- Test compressible and high-entropy labels, backlog recovery, throttling, and mixed receiver versions.
- Compare sample counts end to end.

## Gotchas

- Compression cannot fix cardinality.
- CPU saturation can increase lag.
- Proxy behavior may differ.

## Official sources

- [Official documentation](https://prometheus.io/docs/specs/prw/remote_write_spec/)
