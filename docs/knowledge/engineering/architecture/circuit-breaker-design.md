# circuit-breaker-design

**Issue:** A failing downstream service causes cascading failures upstream
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A payment service timeout causes the checkout service to exhaust its thread pool waiting, eventually taking down the entire API.

## Pattern / Solution
Wrap downstream calls in a circuit breaker with three states: closed (normal), open (failing fast), and half-open (probing recovery). Open the circuit after a failure threshold. Return a fallback response immediately while open. Attempt one probe request in half-open state.

## Gotchas
Circuit breaker state should be per-host, not per-service, to handle partial failures. The fallback must be meaningful returning a blank error is not better than waiting.

## Related
bulkhead-pattern, retry-pattern, fallback-pattern, timeout-pattern
