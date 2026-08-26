# apm-transaction-tracing

**Issue:** Using APM tools to trace individual transactions across services for performance analysis
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A user reports slowness but logs show nothing obviously wrong. Need per-request breakdown of time spent in each service.

## Pattern / Solution
Enable APM tracing (Datadog, New Relic, Elastic APM, or OpenTelemetry). Each request gets a trace ID propagated via HTTP headers. APM collects spans per service: HTTP handler duration, DB query duration, external API call duration, cache lookup. View waterfall trace in APM UI to pinpoint bottleneck. Set performance thresholds — alert when p95 transaction duration exceeds SLO.

## Gotchas
100% trace sampling is expensive at scale — use head-based sampling at 10% for high-traffic services, tail-based sampling to always keep slow/error traces. Ensure trace context propagates through message queues. APM agents add CPU overhead (2-5%).

## Related
opentelemetry-custom-spans, jaeger-tracing-setup, database-query-monitoring, slow-query-logging
