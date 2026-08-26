# kubernetes-readiness-liveness-probes

**Issue:** Correctly configuring readiness, liveness, and startup probes to prevent traffic to unhealthy pods without causing unnecessary restarts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Misconfigured probes are responsible for two common failure modes: (1) liveness probes killing pods that are slow but healthy, causing restart loops; (2) missing readiness probes sending traffic to pods that are starting up or temporarily overloaded.

## Pattern / Solution
**Three probe types and their purposes**

| Probe | Failure action | When to use |
|---|---|---|
| `readinessProbe` | Remove pod from service endpoints | Temporarily not ready (DB connecting, cache warming) |
| `livenessProbe` | Restart the container | Permanently stuck / deadlock |
| `startupProbe` | Restart during startup only | Slow-starting apps (JVM, large model load) |

**Probe implementation — separate endpoints**
```typescript
// Express.js: separate /readyz and /livez handlers
app.get('/livez', (req, res) => {
  // Only check: is the process alive and not deadlocked?
  res.json({ status: 'ok' });
});

app.get('/readyz', async (req, res) => {
  // Check: can this pod serve traffic right now?
  const dbOk = await checkDatabaseConnection();
  const cacheOk = await checkCacheConnection();

  if (!dbOk || !cacheOk) {
    return res.status(503).json({ status: 'not_ready', db: dbOk, cache: cacheOk });
  }
  res.json({ status: 'ok' });
});
```

**Kubernetes probe config with safe defaults**
```yaml
startupProbe:
  httpGet:
    path: /livez
    port: 3000
  failureThreshold: 30   # 30 × 10 s = 5 min startup window
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /readyz
    port: 3000
  initialDelaySeconds: 0  # startupProbe covers early startup
  periodSeconds: 5
  failureThreshold: 3     # 3 × 5 s = 15 s before removing from endpoints
  successThreshold: 1

livenessProbe:
  httpGet:
    path: /livez
    port: 3000
  initialDelaySeconds: 0
  periodSeconds: 10
  failureThreshold: 3     # 3 × 10 s = 30 s before restart
```

## Gotchas
- Never put dependency checks (DB, external API) in a liveness probe — a slow database will cause cascading pod restarts across the cluster
- `readinessProbe` failure does NOT restart the pod — it only removes it from load balancing; the pod continues running
- `startupProbe` disables `livenessProbe` until it succeeds — using both prevents premature liveness kills during startup
- `initialDelaySeconds` is redundant when `startupProbe` is configured; set to 0

## Related
- `kubernetes-rolling-update.md`
- `kubernetes-resource-limits.md`
- `zero-downtime-deployment-checklist.md`
