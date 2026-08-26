# GitHub Actions Service Containers — PostgreSQL, Redis, and Other Docker Sidecars

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Integration tests need a real PostgreSQL database or Redis cache — not a mock or an in-memory stub — but setting up a persistent external service for CI is expensive and creates shared-state problems. Tests that pass locally fail in CI because `localhost:5432` is not available.

GitHub Actions **service containers** start Docker containers alongside the runner job, wired to the same network, so the job's `run:` steps can connect to a real database with a known hostname (`localhost` on docker-based runners, or the service `id` on container-based jobs).

---

## Context

Service containers are defined under `jobs.<job_id>.services`. Each service:
- Is a Docker container started before the first step.
- Remains running for the lifetime of the job.
- Is torn down automatically when the job ends.
- Exposes ports mapped to the host (required for non-container jobs).
- Supports health-check polling so the runner waits until the service is ready.

**Two runner modes affect hostname resolution:**

| Runner type | Job container? | Service hostname |
|---|---|---|
| `ubuntu-latest` (no container) | No | `localhost` |
| `ubuntu-latest` + `container:` | Yes | service `id` (e.g., `postgres`) |

Use `localhost` for most projects — only add a `container:` directive when your build toolchain itself must run inside a specific Docker image.

---

## PostgreSQL Service Container

```yaml
name: Integration tests

on: [push, pull_request]

jobs:
  integration:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U testuser -d testdb"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20

      - run: npm ci

      - name: Run database migrations
        run: npm run db:migrate

      - name: Run integration tests
        run: npm test -- --testPathPattern=integration
```

Notes:
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` are standard Postgres image env vars.
- `--health-cmd` uses `pg_isready` (built into the Postgres image). Without a health check the runner starts steps immediately and tests fail on "connection refused" because Postgres hasn't finished initialising.
- `--health-retries 5` with a 10s interval means the runner waits up to ~60 s before declaring the service unhealthy and failing the job.
- Port mapping `5432:5432` maps container port to host port; required on non-container jobs.

---

## Redis Service Container

```yaml
jobs:
  test:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 3

    env:
      REDIS_URL: redis://localhost:6379

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest tests/integration/
```

Redis has no built-in wait mechanism, so the `redis-cli ping` health check is essential. Without it, jobs that import Redis modules during startup fail with `ECONNREFUSED`.

---

## Multiple Services: PostgreSQL + Redis + MinIO

```yaml
jobs:
  full-stack-test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: appdb
          POSTGRES_USER: app
          POSTGRES_PASSWORD: secret
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U app -d appdb"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 5

      minio:
        image: bitnami/minio:latest
        env:
          MINIO_ROOT_USER: minioadmin
          MINIO_ROOT_PASSWORD: minioadmin
        ports:
          - 9000:9000
        options: >-
          --health-cmd "curl -f http://localhost:9000/minio/health/live"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql://app:secret@localhost:5432/appdb
      REDIS_URL: redis://localhost:6379
      S3_ENDPOINT: http://localhost:9000
      S3_ACCESS_KEY: minioadmin
      S3_SECRET_KEY: minioadmin
      S3_BUCKET: test-bucket

    steps:
      - uses: actions/checkout@v4

      - name: Create MinIO test bucket
        run: |
          curl -s https://dl.min.io/client/mc/release/linux-amd64/mc \
            -o /usr/local/bin/mc && chmod +x /usr/local/bin/mc
          mc alias set local http://localhost:9000 minioadmin minioadmin
          mc mb local/test-bucket --ignore-existing

      - run: npm ci
      - run: npm run db:migrate
      - run: npm test
```

---

## Using Services with a Container Job (Hostname Changes)

When the job itself runs inside a container (`container:` key), service containers are on the same Docker network and the service is reachable by its YAML key name, not `localhost`:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest

    container:
      image: node:20-alpine

    services:
      db:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: secret
        options: >-
          --health-cmd "pg_isready"
          --health-interval 10s
          --health-retries 5
        # No ports: mapping needed — container-to-container uses Docker network

    env:
      # Note: hostname is "db" (the service id), NOT "localhost"
      DATABASE_URL: postgresql://postgres:secret@db:5432/postgres

    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test
```

The absence of a `ports:` block is intentional: containers on the same job network communicate directly by service name. Port mapping is only required when the host runner (non-container) needs to reach the service via `localhost`.

---

## Seeding a Database Before Tests

For complex schemas, run migrations or seed scripts in a dedicated step before tests:

```yaml
steps:
  - uses: actions/checkout@v4

  - name: Wait for Postgres to be ready
    # Health checks handle readiness, but an explicit step helps debugging
    run: |
      until pg_isready -h localhost -p 5432 -U testuser; do
        echo "Waiting for Postgres..."
        sleep 2
      done

  - name: Run migrations
    env:
      DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
    run: npx prisma migrate deploy

  - name: Seed test data
    env:
      DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
    run: npx prisma db seed

  - name: Run tests
    env:
      DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
    run: npm test
```

---

## Anti-patterns

- **Omitting health checks.** Service containers start asynchronously. Without `--health-cmd`, steps begin immediately and connection errors cause flaky test failures. Always add a health check for any service that has a startup delay.

- **Hardcoding `localhost` in the test source code.** Connection strings should come from environment variables. Hardcoding `localhost` breaks container-based jobs where the hostname is the service ID.

- **Using a non-existent or private image without authentication.** If the image requires a DockerHub login, add a `docker login` step before the job's `services:` are started — but services spin up before steps, so you cannot log in first. For private images, configure registry credentials in the service's `credentials:` block:

```yaml
services:
  myservice:
    image: registry.example.com/private/image:latest
    credentials:
      username: ${{ secrets.REGISTRY_USER }}
      password: ${{ secrets.REGISTRY_PASSWORD }}
```

- **Running migration tools that assume an empty database without wiping first.** Services persist for the job but each job run starts fresh containers, so the database is always empty at the start. If you add a re-run step that calls `migrate up` twice, the second run may fail on duplicate objects. Use `migrate reset` or idempotent migration scripts.

- **Over-provisioning services in the matrix.** If you have a matrix of 6 combinations all requiring Postgres, 6 Postgres containers spin up simultaneously on the same runner host. Consider collapsing integration test jobs into a single job that runs multiple test suites sequentially to avoid memory exhaustion.

---

## Gotchas

- **`options:` accepts Docker CLI flags as a single string.** Use the `>-` YAML block scalar (literal block without trailing newline) to keep the flags readable across multiple lines without introducing shell newlines. Each flag must be a space-separated token; no shell escaping is interpreted.

- **Port conflicts on self-hosted runners.** On self-hosted runners, ports mapped to the host persist after the job if Docker cleanup fails. Use dynamic port mapping (`- 5432` without a host port) and read the assigned port from `${{ job.services.postgres.ports['5432'] }}`.

- **`POSTGRES_HOST_AUTH_METHOD: trust` trades convenience for security.** Setting this env var eliminates the password requirement. Fine for ephemeral CI containers but never carry this pattern to any non-CI environment.

- **Service container logs are not surfaced by default.** When a health check fails and the job errors on "service unhealthy", the Docker logs from the service container are not shown. Add a step to print them for debugging:

```yaml
- name: Print Postgres logs on failure
  if: failure()
  run: docker logs $(docker ps -q --filter ancestor=postgres:16-alpine) 2>&1 || true
```

- **Services do not share a volume with the job steps.** You cannot mount the repo checkout into a service container. Pre-seed data via network connections (SQL scripts via `psql`, REST calls, etc.), not via shared filesystem mounts.

---

## Verification

```yaml
- name: Verify Postgres connectivity
  run: |
    psql "$DATABASE_URL" -c "SELECT version();"

- name: Verify Redis connectivity
  run: |
    redis-cli -u "$REDIS_URL" ping | grep -q PONG && echo "Redis OK"
```

Check service health status in Actions logs under **Set up job → Initialize containers** — each service shows "Healthy" or "Unhealthy" with the health check output.

---

## Related

- `github-actions-e2e-playwright.md` — browser testing that also benefits from service containers
- `github-actions-environment-protection.md` — isolating production vs. test environments
- `github-actions-concurrency-groups.md` — preventing parallel jobs from competing for shared ports
- `github-actions-self-hosted-runners.md` — service container behaviour differences on self-hosted
- `github-actions-matrix-strategy-dynamic-workflows.md` — parallelising test suites

---

## Sources

- GitHub Docs: "About service containers" — https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/about-service-containers
- GitHub Docs: "Creating PostgreSQL service containers" — https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/creating-postgresql-service-containers
- GitHub Docs: "Creating Redis service containers" — https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/creating-redis-service-containers
- Docker Healthcheck documentation — https://docs.docker.com/engine/reference/builder/#healthcheck
