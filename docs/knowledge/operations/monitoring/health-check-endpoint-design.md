# health-check-endpoint-design

**Issue:** Designing /health and /ready endpoints that accurately reflect service state
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Load balancers and orchestrators need reliable signals to route traffic correctly; naive health checks mask real problems.

## Pattern / Solution
Implement two endpoints: /healthz (liveness) returns 200 if process is alive — minimal checks only, never block. /readyz (readiness) checks all dependencies and returns 200 only when ready to serve traffic. Response body: {status: 'ok', checks: {db: 'ok', cache: 'degraded'}, version: '1.2.3'}. Keep checks fast under 200ms per dependency.

## Gotchas
Never check upstream services in liveness probes — a flaky downstream will restart your pod unnecessarily. Readiness probe failures should remove the pod from load balancer rotation, not restart it. Rate-limit health endpoints to prevent check storms.

## Related
readiness-vs-liveness-probes, uptime-monitoring-patterns, blackbox-monitoring
