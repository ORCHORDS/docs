# rate-limiting-architecture

**Issue:** A single client can exhaust API capacity and degrade service for others
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A misconfigured bot hammers an endpoint, causing elevated latency for all users.

## Pattern / Solution
Apply rate limits at the API gateway using token bucket or sliding window algorithms. Limit by API key, user ID, and IP. Return 429 with Retry-After headers. Use a shared counter store like Redis for distributed enforcement across gateway replicas.

## Gotchas
Per-IP limiting breaks legitimate clients behind NAT. Always offer per-API-key limits as the primary mechanism. Implement tiered limits for different subscription levels.

## Related
throttling-patterns, load-shedding-patterns, api-gateway-pattern
