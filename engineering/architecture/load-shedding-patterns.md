# load-shedding-patterns

**Issue:** Overloaded systems degrade for all users instead of maintaining service for some
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
During a traffic spike the entire API slows to unusable rather than serving a subset of requests at full speed.

## Pattern / Solution
Reject low-priority requests when load exceeds capacity thresholds. Prioritize requests by user tier, request type, or queue age. Return 503 with a Retry-After header. Prefer shedding to queueing beyond a threshold to avoid latency amplification.

## Gotchas
Define shedding priorities before an incident, not during. Test load shedding behavior in staging. Ensure health checks are exempt from shedding so load balancers receive accurate signals.

## Related
rate-limiting-architecture, throttling-patterns, backpressure-patterns
