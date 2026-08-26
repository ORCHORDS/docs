# readiness-vs-liveness-probes

**Issue:** Correctly configuring Kubernetes liveness and readiness probes to avoid cascading restarts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Pods restart when they should only be removed from rotation, or stay in rotation while initializing. Misconfigured probes cause instability.

## Pattern / Solution
Liveness probe: restart the container if it fails. Use for detecting deadlocks or unrecoverable states. Check only the process itself. Readiness probe: remove from Service endpoints if it fails. Use for checking if the app can serve traffic. Startup probe: give slow-starting containers time before liveness kicks in. Set initialDelaySeconds greater than your worst-case startup time.

## Gotchas
Failing liveness probes cause restarts which can mask underlying issues — check pod restart counts. Set failureThreshold high enough to tolerate transient dependency blips. Readiness failures on all pods simultaneously will drop all traffic.

## Related
health-check-endpoint-design, uptime-monitoring-patterns
