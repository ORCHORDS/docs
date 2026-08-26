# service-dependency-startup-order

**Issue:** Ensuring services start in the correct order when dependencies are not yet ready
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Apps that connect to a database or message broker on startup crash with connection refused if the dependency is not ready. Kubernetes does not enforce inter-pod startup order natively.

## Pattern / Solution
Init containers to wait for dependencies:
```yaml
initContainers:
- name: wait-for-postgres
  image: busybox:1.36
  command: ['sh', '-c',
    'until nc -z postgres-service 5432; do echo waiting for postgres; sleep 2; done']

- name: wait-for-redis
  image: busybox:1.36
  command: ['sh', '-c',
    'until nc -z redis-service 6379; do echo waiting for redis; sleep 2; done']

containers:
- name: api
  image: myorg/api:latest
  # Starts only after all initContainers succeed
```

Application-level retry with backoff (preferred pattern):
```python
import time
import psycopg2
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=2, max=30)
)
def connect_db():
    return psycopg2.connect(DATABASE_URL)

# Called at startup — retries automatically
conn = connect_db()
```

Docker Compose depends_on with health check:
```yaml
services:
  db:
    image: postgres:16
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres"]
      interval: 5s
      timeout: 3s
      retries: 10

  api:
    image: myorg/api:latest
    depends_on:
      db:
        condition: service_healthy
```

wait-for-it.sh script:
```dockerfile
COPY wait-for-it.sh /usr/local/bin/
CMD ["wait-for-it.sh", "postgres:5432", "--", "node", "server.js"]
```

## Gotchas
- `depends_on` (without `condition: service_healthy`) only waits for the container to start, not for the service to be ready
- Init containers count toward pod startup time; long `wait` loops delay readiness even when all deps are up
- Application-level retry is more resilient than startup ordering — a dependency can go down and recover without pod restart
- Circular dependencies (A waits for B, B waits for A) deadlock; break the cycle by making one service tolerant of the other being absent
- In Kubernetes, init containers restart from the beginning on failure — ensure they are idempotent

## Related
- `health-check-readiness-patterns.md`
- `kubernetes-readiness-liveness-probes.md`
- `docker-compose-production.md`
- `graceful-shutdown-patterns.md`
