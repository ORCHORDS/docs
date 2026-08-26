# zero-downtime-deployment-checklist

**Issue:** Steps to verify before, during, and after any production deploy to avoid user-visible outages
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deployments cause brief service interruptions — 502 errors, dropped connections, failed health checks — that erode user trust. A repeatable pre/post checklist catches the common failure modes before they reach production.

## Pattern / Solution
**Pre-deploy**
- [ ] Feature flags disabled for in-flight changes
- [ ] Database migrations are backward-compatible (no column drops, no NOT NULL without default)
- [ ] Old and new code can run simultaneously (both read the same schema)
- [ ] Load balancer health-check path returns 200 on new image before traffic shifts
- [ ] Deployment window communicated to on-call

**During deploy**
- [ ] Rolling update — never terminate all old pods before new ones are healthy
- [ ] `minReadySeconds` / `startupProbe` give containers time to warm up
- [ ] Watch error rate dashboard in real time; abort if p99 latency spikes > 2×

**Post-deploy**
- [ ] Smoke tests pass against production (see `deployment-verification-smoke-tests.md`)
- [ ] SLO dashboards green for 10 minutes
- [ ] Old replica set / task definition cleaned up
- [ ] Deployment entry written to the incident log

```yaml
# Kubernetes rolling update settings that enforce zero-downtime
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

## Gotchas
- `maxUnavailable: 0` means deploys are slower but never drop below desired capacity
- Long-lived websocket connections will still be terminated when old pods die; plan reconnect logic on the client
- Health check must probe actual app readiness, not just "process is up"
- Caches primed on first request can cause latency spikes on pod startup — use `startupProbe` with a longer `failureThreshold`

## Related
- `deployment-verification-smoke-tests.md`
- `rollback-runbook.md`
- `kubernetes-readiness-liveness-probes.md`
- `zero-downtime-deploys.md`
