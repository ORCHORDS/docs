# gc-pressure-monitoring

**Issue:** Monitoring garbage collection overhead to detect when GC is degrading application throughput
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
High latency spikes correlate with nothing in application code. GC pauses are the hidden cause.

## Pattern / Solution
Instrument GC metrics per runtime: JVM (jvm_gc_pause_seconds), Go (go_gc_duration_seconds), Node.js (V8 GC stats via perf_hooks). Alert when GC pause p99 exceeds 100ms or GC overhead exceeds 10% of wall time. Track heap allocation rate — rapid allocation drives GC frequency. Use GC logs for detailed analysis.

## Gotchas
High GC pressure is a symptom, not a root cause — trace allocation hotspots. Reducing object allocation rate is more effective than tuning GC parameters. In JVM, G1GC region sizing affects pause times significantly. Node.js V8 does not expose detailed GC metrics by default.

## Related
memory-leak-detection, worker-cpu-monitoring, apm-transaction-tracing
