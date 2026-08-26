# circuit-breaker-prevents-cascade-failure

**Issue:** A failing downstream service takes down the entire system when callers retry indefinitely without a circuit breaker
**Date:** 2026-08-11
**Status:** documented

## What happened
A recommendations service became slow due to a memory leak. Every API request called the recommendations service and waited for a 30-second timeout before giving up. With thousands of concurrent users, all worker threads were blocked waiting for the slow service. The main application became unresponsive even though recommendations were optional. One degraded service cascaded into a full outage.

## The lesson
Use a circuit breaker around every external service call. When the error rate or latency exceeds a threshold, the circuit opens and calls immediately return a fallback (empty recommendations, cached data, or a graceful degradation) without waiting. This isolates failures to the broken service.

## Why it matters
Cascading failures are the most common cause of large-scale outages. A circuit breaker is the single most effective pattern for preventing a degraded dependency from taking down your entire system.

## How to apply
- [ ] Identify every external dependency (database, third-party API, microservice, cache).
- [ ] Wrap each with a circuit breaker with configurable thresholds (e.g., open after 50% error rate over 10 seconds).
- [ ] Define a fallback for each circuit: cached result, empty response, or graceful error message.
- [ ] Add circuit state to your health check endpoint and monitoring dashboard.
- [ ] Test circuit breaker behavior by deliberately taking a dependency down in staging.

## Related
- `timeouts-everywhere-no-exceptions.md`
- `health-checks-must-check-dependencies.md`
- `rate-limit-before-you-need-it.md`
