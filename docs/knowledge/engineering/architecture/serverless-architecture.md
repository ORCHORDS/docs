# serverless-architecture

**Issue:** Managing infrastructure for spiky, event-driven workloads is expensive and operationally complex
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A webhook processing service needs to scale from zero to thousands of events per second and back, but running dedicated VMs is wasteful.

## Pattern / Solution
Use functions-as-a-service (Lambda, Cloud Functions) triggered by events. Pay per invocation. Auto-scale to zero. Combine with managed queues, object storage, and managed databases for stateless function design.

## Gotchas
Cold starts add latency. Execution time limits constrain long-running tasks. Vendor lock-in is significant. Observability requires explicit instrumentation since logs are per-invocation.

## Related
function-as-a-service-patterns, event-driven-architecture, edge-computing-patterns
