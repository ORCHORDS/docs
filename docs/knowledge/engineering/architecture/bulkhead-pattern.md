# bulkhead-pattern

**Issue:** A single slow operation consumes all shared resources and starves other operations
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A batch export endpoint uses the same thread pool as the interactive API. A large export causes latency spikes for all users.

## Pattern / Solution
Isolate resource pools by operation category. Assign separate thread pools, connection pools, or queue consumers to distinct workload types. A bulkhead failure is contained to its compartment.

## Gotchas
Too many pools fragment resources unnecessarily. Start with coarse isolation (interactive vs. background) and split further only when measured contention justifies it.

## Related
circuit-breaker-design, rate-limiting-architecture, load-shedding-patterns
