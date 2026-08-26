# observability-three-pillars-overview

**Issue:** Understanding the three pillars of observability: metrics, logs, and traces
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams struggle to diagnose production issues because they lack a cohesive observability strategy. Knowing which pillar to reach for and when is foundational.

## Pattern / Solution
The three pillars work together:
- **Metrics** — numeric time-series data (counters, gauges, histograms). Low cost, high cardinality aggregation, ideal for alerting.
- **Logs** — structured or unstructured text events. High detail per event, expensive at scale.
- **Traces** — distributed request flows across services. Pinpoints latency and error propagation.

```text
Metrics  → "Is something wrong?"
Logs     → "What happened?"
Traces   → "Where did it happen?"
```

Instrument all three and correlate them via shared identifiers (trace_id, request_id).

## Gotchas
- Metrics alone cannot explain *why* an anomaly occurred
- Logs without structure (unstructured text) become unsearchable at volume
- Traces without sampling strategy become prohibitively expensive
- Treat correlation IDs as first-class citizens from day one

## Related
- `metrics-vs-logs-vs-traces.md`
- `opentelemetry-overview.md`
- `log-correlation-ids.md`
