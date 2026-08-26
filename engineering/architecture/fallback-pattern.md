# fallback-pattern

**Issue:** A service dependency failure has no graceful degradation path
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The recommendations service goes down and the homepage shows a blank widget instead of a default list.

## Pattern / Solution
Define a fallback for every external dependency call. Fallbacks can be: cached stale data, a static default, a simplified local computation, or a graceful empty state. Implement fallbacks at the same layer as circuit breakers.

## Gotchas
Fallbacks that silently return empty data can mask outages. Always emit a metric or log when a fallback activates. Do not use fallbacks as a substitute for fixing reliability issues.

## Related
circuit-breaker-design, bulkhead-pattern, cache-aside-pattern
