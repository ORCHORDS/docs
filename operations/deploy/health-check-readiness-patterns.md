# health-check-readiness-patterns

**Issue:** Designing health check endpoints that accurately reflect service readiness and liveness
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Shallow health checks that always return 200 cause traffic to be routed to broken services. Deep checks that query the database on every probe cause DB load and false cascading failures.

## Pattern / Solution
Three-tier health endpoint pattern:
```javascript
// /live — is the process running? (Kubernetes livenessProbe)
// Never check external dependencies here — a DB outage should not restart the pod
app.get('/live', (req, res) => {
  res.json({ status: 'alive', pid: process.pid });
});

// /ready — can this instance serve traffic? (Kubernetes readinessProbe)
// Check critical dependencies; fail here to pull pod from LB rotation
app.get('/ready', async (req, res) => {
  const checks = await Promise.allSettled([
    checkDatabaseConnection(),   // select 1
    checkRedisConnection(),      // ping
  ]);

  const failures = checks
    .map((c, i) => c.status === 'rejected' ? ['db', 'redis'][i] : null)
    .filter(Boolean);

  if (failures.length > 0) {
    return res.status(503).json({ status: 'not ready', failures });
  }
  res.json({ status: 'ready' });
});

// /health — detailed status for monitoring dashboards (not used by Kubernetes)
app.get('/health', async (req, res) => {
  const dbMs = await measureQuery('SELECT 1');
  res.json({
    status: 'ok',
    version: process.env.IMAGE_TAG,
    uptime: process.uptime(),
    dependencies: {
      database: { latencyMs: dbMs },
    }
  });
});
```

Database check with timeout:
```javascript
async function checkDatabaseConnection() {
  return Promise.race([
    pool.query('SELECT 1'),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error('DB check timeout')), 2000)
    )
  ]);
}
```

Kubernetes probe config aligned with the pattern:
```yaml
livenessProbe:
  httpGet:
    path: /live
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 2
```

## Gotchas
- A failing `livenessProbe` restarts the pod; a failing `readinessProbe` only removes it from endpoints — never conflate the two
- Readiness checks that call external services create a dependency chain: if the DB is slow, all pods become unready simultaneously
- Cache the result of expensive readiness checks (e.g., for 5 seconds) to avoid thundering herd on the DB under probe frequency
- `/health` endpoints should not require authentication; put them on a separate port or path outside the auth middleware

## Related
- `docker-healthcheck-patterns.md`
- `kubernetes-readiness-liveness-probes.md`
- `service-dependency-startup-order.md`
