# observability-architecture

**Issue:** Production failures are diagnosed by guesswork because there is insufficient telemetry
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An on-call engineer cannot determine whether a latency spike is caused by a slow database query, a memory leak, or a downstream dependency without SSH-ing into servers.

## Pattern / Solution
Implement the three pillars: structured logs (correlated by trace ID), distributed traces (spans across service boundaries), and metrics (RED: rate, errors, duration per endpoint). Store in a centralized observability platform. Define SLOs and alert on burn rate.

## Gotchas
High-cardinality labels in metrics explode storage costs. Sampling distributed traces must be consistent to preserve trace completeness. Alert on symptoms (SLO burn) not causes (CPU usage) to reduce noise.

## Related
a-b-testing-architecture, canary-deployment-architecture, disaster-recovery-architecture
