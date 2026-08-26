# timeout-pattern

**Issue:** Hung downstream calls block resources indefinitely
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A database query with no timeout causes connection pool exhaustion after a slow query plan regression.

## Pattern / Solution
Set timeouts at every I/O boundary: connect timeout, read timeout, and overall deadline. Propagate deadlines through context objects. Use deadline propagation across service boundaries via headers or gRPC metadata.

## Gotchas
Timeouts that are too aggressive cause false failures during legitimate slow operations. Calibrate from p99 latency histograms, not p50. Missing connection timeouts are a common omission.

## Related
circuit-breaker-design, retry-pattern, bulkhead-pattern
