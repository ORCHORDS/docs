# OpenTelemetry Collector backpressure, persistent queues, and loss budgets

**Issue:** A telemetry backend outage turns into memory exhaustion, silent data loss, or an unbounded retry storm in collectors.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Design each OpenTelemetry Collector export path with an explicit loss budget, bounded queues, retry behavior, and receiver backpressure. Use persistent queues only after validating their storage, failure, and privacy characteristics.

## Resiliency model

Collector resiliency combines exporter retries, sending queues, memory protection, and receiver-side flow control. The components must agree: a queue can buffer a transient outage, but it cannot turn an unavailable backend into infinite capacity.

## Operating checklist

1. Define which signals may be sampled or dropped and which are business/security critical.
2. Configure bounded retry and queue capacity from measured ingest rate and a finite outage window.
3. Use memory protection to prevent telemetry pressure from destabilizing the workload.
4. When persistent queues are required, monitor storage capacity and recovery behavior; test a restart during an outage.
5. Expose queue size, refused/dropped data, retry outcomes, exporter failures, and receiver backpressure in dashboards.
6. Exercise overload and backend-failure tests before raising queue capacity in production.

## Guardrails

- A larger queue delays loss; it does not solve a sustained backend failure.
- Persistent queue contents can carry sensitive telemetry and need the same access/retention controls as the backend.
- Do not blindly retry non-retryable errors.
- Verify behavior with the exact Collector distribution and component versions you deploy.

## Sources

- [OpenTelemetry Collector resiliency](https://opentelemetry.io/docs/collector/resiliency/)
