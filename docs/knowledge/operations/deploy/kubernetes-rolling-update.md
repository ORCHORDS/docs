# kubernetes-rolling-update

**Issue:** Configuring Kubernetes rolling updates to deploy without downtime and with safe rollback
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The default Kubernetes rolling update settings allow up to 25% of pods to be unavailable during a deploy, which can cause a visible outage on low-replica deployments. Tuning the strategy and probes ensures pods are replaced gracefully.

## Pattern / Solution
**Deployment strategy configuration**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # one extra pod allowed during rollout
      maxUnavailable: 0  # never go below desired replica count
  minReadySeconds: 10    # pod must stay ready for 10s before counted as available
  progressDeadlineSeconds: 300  # fail the rollout if not complete in 5 min
```

**Probes that enable safe rolling updates**
```yaml
containers:
  - name: api
    readinessProbe:
      httpGet:
        path: /readyz
        port: 3000
      initialDelaySeconds: 5
      periodSeconds: 5
      failureThreshold: 3
    livenessProbe:
      httpGet:
        path: /livez
        port: 3000
      initialDelaySeconds: 15
      periodSeconds: 10
      failureThreshold: 3
    startupProbe:       # for slow-starting containers
      httpGet:
        path: /livez
        port: 3000
      failureThreshold: 30   # 30 × 10s = 5 min startup budget
      periodSeconds: 10
```

**Triggering and monitoring a rollout**
```bash
# Trigger rollout by updating image
kubectl set image deployment/api api=ghcr.io/org/api:v2.41.3 -n prod

# Watch progress
kubectl rollout status deployment/api -n prod

# Pause if something looks wrong mid-rollout
kubectl rollout pause deployment/api -n prod

# Resume
kubectl rollout resume deployment/api -n prod

# Roll back
kubectl rollout undo deployment/api -n prod
```

## Gotchas
- `maxUnavailable: 0` requires `replicas >= 2`; on a single-replica deployment it will always cause a brief gap
- The `readinessProbe` is what gates traffic routing — a misconfigured probe is the most common cause of 502s during rolling updates
- `minReadySeconds` is counted after readiness, not after startup — set it to at least one probe cycle
- Terminating pods get a `SIGTERM`; ensure the app handles graceful shutdown (drain in-flight requests before exiting)

## Related
- `kubernetes-readiness-liveness-probes.md`
- `kubernetes-resource-limits.md`
- `rollback-runbook.md`
- `zero-downtime-deployment-checklist.md`
