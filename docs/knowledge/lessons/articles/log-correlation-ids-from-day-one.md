# log-correlation-ids-from-day-one

**Issue:** Distributed systems without correlation IDs make cross-service incident investigation impossibly slow
**Date:** 2026-08-11
**Status:** documented

## What happened
A checkout failure was reported. The request touched six microservices. Each service logged independently with different timestamps and no shared identifier. Reconstructing the request path took four hours of manual log correlation across Kibana, Splunk, and CloudWatch. The actual bug fix took 20 minutes.

## The lesson
Generate a UUID correlation ID at the edge (API gateway or first service) and propagate it in every downstream HTTP call header (`X-Correlation-ID` or `traceparent`). Every log line in every service must include it. This is not optional and cannot be retrofitted cheaply — do it on day one.

## Why it matters
Without a correlation ID, debugging a distributed failure is archaeology. With one, it is a filtered log query. The difference is hours of engineer time per incident.

## How to apply
- [ ] Generate a UUID at the API gateway for every inbound request if no `X-Correlation-ID` header is present.
- [ ] Pass the ID in every outbound HTTP request and message queue message.
- [ ] Configure logging middleware to inject the ID into every log line automatically (not per-call).
- [ ] Use OpenTelemetry `traceparent` if you already have distributed tracing — it carries correlation natively.
- [ ] Verify in integration tests that the ID appears in logs from all services for a single request.

## Related
- `audit-logs-are-append-only.md`
- `health-checks-must-check-dependencies.md`
