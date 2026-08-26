# whitebox-monitoring

**Issue:** Monitoring internal application state via metrics, logs, and traces emitted by the service itself
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
External probes show service is up but internal errors, slow queries, or queue backlogs are invisible without instrumentation.

## Pattern / Solution
Instrument code to emit: counters for request and error counts, histograms for latency, gauges for queue depths and pool sizes. Use Prometheus client libraries or OpenTelemetry SDK. Expose /metrics endpoint. Add structured logs with request IDs. Emit traces for distributed request flows. Alert on derived signals like error rate.

## Gotchas
Whitebox monitoring requires code changes — build instrumentation into your development process. Too many metrics causes cardinality explosion. Choose what to instrument based on SLOs. Combine with blackbox monitoring for complete coverage.

## Related
blackbox-monitoring, opentelemetry-overview, prometheus-setup-basics, sli-slo-sla-definitions
