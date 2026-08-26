# docker-healthcheck-patterns

**Issue:** Writing effective Docker HEALTHCHECK instructions for reliable container lifecycle management
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Containers without health checks are treated as healthy immediately after start. Orchestrators route traffic to unhealthy containers and cannot restart them automatically. Kubernetes uses its own probes, but health checks matter for docker-compose and ECS deployments.

## Pattern / Solution
HTTP health check in Dockerfile:
```dockerfile
FROM node:20-alpine
# Install curl for health check
RUN apk add --no-cache curl

COPY . .
RUN npm ci --production

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

EXPOSE 3000
CMD ["node", "server.js"]
```

Lightweight health endpoint (avoid expensive DB checks in HEALTHCHECK):
```javascript
// /health — fast shallow check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', uptime: process.uptime() });
});

// /ready — deep check (use for Kubernetes readinessProbe, not HEALTHCHECK)
app.get('/ready', async (req, res) => {
  const dbOk = await checkDatabase();
  if (!dbOk) return res.status(503).json({ status: 'not ready' });
  res.json({ status: 'ready' });
});
```

TCP-only health check (no curl needed):
```dockerfile
HEALTHCHECK CMD nc -z localhost 5432 || exit 1
```

Shell-based check for non-HTTP services:
```dockerfile
HEALTHCHECK --interval=10s CMD pg_isready -U postgres || exit 1
```

Override in docker-compose:
```yaml
services:
  api:
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8080/health || exit 1"]
      interval: 20s
      timeout: 3s
      retries: 5
      start_period: 30s
```

## Gotchas
- `--start-period` delays health check evaluation (not execution); the first N failures during start-period do not count
- A container is `unhealthy` after `retries` consecutive failures; it stays running — orchestrators decide what to do
- Avoid `curl` in minimal images (distroless, scratch); use `wget`, `nc`, or a compiled binary health check tool
- Health checks running as root in a rootless container require the binary to be available to that user
- Do not make HEALTHCHECK call external services; it should test only what this container owns

## Related
- `docker-compose-production.md`
- `health-check-readiness-patterns.md`
- `kubernetes-readiness-liveness-probes.md`
