# docker-compose-production

**Issue:** Hardening docker-compose for production single-host deployments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Docker Compose is often used in production for small services or internal tools. Default configurations are permissive and lack restart policies, resource limits, and security hardening.

## Pattern / Solution
Production-grade compose file:
```yaml
version: "3.9"
services:
  api:
    image: ghcr.io/myorg/api:${IMAGE_TAG:?IMAGE_TAG required}
    restart: unless-stopped
    read_only: true
    tmpfs: [/tmp]
    security_opt:
      - no-new-privileges:true
    user: "1000:1000"
    environment:
      - DB_PASSWORD_FILE=/run/secrets/db_password
    secrets:
      - db_password
    ports:
      - "127.0.0.1:8080:8080"   # bind to localhost only; use reverse proxy
    networks:
      - internal
    deploy:
      resources:
        limits:
          cpus: "2"
          memory: 512M
        reservations:
          cpus: "0.5"
          memory: 128M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    networks:
      - internal

secrets:
  db_password:
    external: true   # pre-created: docker secret create db_password -

networks:
  internal:
    driver: bridge
    internal: true   # no external internet access

volumes:
  pgdata:
```

Deploy:
```bash
IMAGE_TAG=abc1234 docker compose -f docker-compose.prod.yml up -d --pull always
docker compose ps
docker compose logs --tail=50 api
```

## Gotchas
- `deploy.resources` is only honored by Docker Swarm; for standalone Compose use `mem_limit`/`cpus` at service level
- `ports: "8080:8080"` binds to 0.0.0.0 by default; always prefix with `127.0.0.1:` in production
- Secrets via `_FILE` convention require the application to read the file; not all images support this
- `restart: always` will restart containers that exit 0 (success); prefer `unless-stopped`
- `read_only: true` causes failures if the app writes to its filesystem; add `tmpfs` mounts for writable dirs

## Related
- `docker-healthcheck-patterns.md`
- `docker-volume-management.md`
- `docker-network-modes.md`
- `docker-security-scanning.md`
