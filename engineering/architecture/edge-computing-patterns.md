# edge-computing-patterns

**Issue:** Latency-sensitive logic running at origin adds unnecessary round-trip time
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A geo-redirect, A/B assignment, or auth token validation adds a full origin round-trip to every request.

## Pattern / Solution
Move lightweight logic to the edge using Cloudflare Workers, AWS Lambda@Edge, or Fastly Compute. Edge functions run within milliseconds of the user. Use edge KV stores for routing tables and feature flags.

## Gotchas
Edge runtimes have constrained APIs (no full Node.js). Cold starts on infrequently hit edges can spike latency. Debug tooling at the edge is immature compared to origin.

## Related
cdn-architecture, serverless-architecture, feature-flag-architecture
