# log-correlation-ids

**Issue:** Propagating request IDs through logs and traces to correlate events across services
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A user reports an error. You can find the error log but cannot find all related logs across services for the same request.

## Pattern / Solution
Generate a unique request ID at the edge (load balancer or API gateway). Propagate via HTTP header (X-Request-ID or W3C traceparent). In each service extract the ID and add to all log entries as trace_id. Propagate through async calls: include in message queue payloads and background job arguments. In Loki query by trace_id to find all logs for a request.

## Gotchas
OpenTelemetry trace context (traceparent header) provides both trace ID and span ID — prefer this over custom headers. Background jobs lose request context — generate a new job-scoped ID and log the originating request ID. Log sampling must preserve all logs for sampled trace IDs.

## Related
log-structured-logging, log-sampling-strategies, opentelemetry-baggage-propagation, loki-logql-queries
