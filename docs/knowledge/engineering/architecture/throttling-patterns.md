# throttling-patterns

**Issue:** Bursty clients overload backends that cannot absorb sudden spikes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A nightly batch job sends 10,000 requests in seconds, causing queue saturation in the processing backend.

## Pattern / Solution
Throttle at the client side using token buckets or leaky buckets to smooth bursts. On the server side, use adaptive throttling based on current system load. Queue excess requests rather than rejecting immediately when queue depth allows.

## Gotchas
Server-side throttling without client cooperation causes retry storms. Provide a client library that enforces rate limits locally before requests leave the process.

## Related
rate-limiting-architecture, backpressure-patterns, load-shedding-patterns
