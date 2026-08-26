# OpenTelemetry group-by-trace capacity controls

**Issue:** Processors that require complete traces can make wrong decisions when spans reach different collectors, arrive late, or exceed in-memory trace capacity.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Route every span for a trace to the same Collector instance, then configure groupbytrace wait_duration, num_traces, and num_workers from measured trace rates and arrival distributions. Place batch after groupbytrace, not before it. Treat release after the wait as a heuristic rather than proof of completeness and define restart loss semantics because the processor is stateful.

## Verification

Replay complete, late, split-routed, oversized, and never-completing traces. Drive capacity eviction and verify traces_evicted, incomplete_releases, traces-in-memory, queue depth, and event latency alarms. Test scaling and rolling restarts.

## Gotchas

- Pin and verify exact platform versions before rollout.
- Preserve reproducible diagnostics without secrets or personal data.
- Define rollback and stop conditions before production use.

## Official source

- [Primary documentation](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/groupbytraceprocessor/README.md)
