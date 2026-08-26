# memory-leak-detection

**Issue:** Identifying and alerting on gradual memory growth indicating leaks in long-running processes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Process memory grows over days until OOM kill. No single request causes it — it is cumulative.

## Pattern / Solution
Track container_memory_working_set_bytes over time. A leak shows as monotonically increasing RSS across multiple GC cycles. Alert on growth rate using deriv() over 1h window. Use heap profiling on suspected leaks: Node.js v8.writeHeapSnapshot(), Go pprof.WriteHeapProfile(). Correlate growth with request count to identify per-request leak.

## Gotchas
Memory growth is not always a leak — caches fill legitimately. Distinguish between RSS and heap. GC pauses can look like memory spikes. Set memory limits with 20% headroom and alert at 80% before OOM.

## Related
gc-pressure-monitoring, worker-cpu-monitoring, cpu-throttling-detection
