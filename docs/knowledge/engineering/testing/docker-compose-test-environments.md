# Docker Compose Test Environment Isolation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Integration tests pass on one engineer's laptop and fail on another because their local Postgres is a different version, or Redis is already running on the default port with leftover data from a prior session. On CI, two parallel jobs step on each other's databases. You need a reproducible, isolated environment for each test run that starts clean, uses the correct service versions, and tears itself down automatically — without requiring a full Kubernetes cluster or Docker-in-Docker.

Docker Compose (v2, the `docker compose` plugin) solves this for local dev and CI with a declarative file that makes the full stack reproducible.

## Context

`docker compose` provisions a private network and named containers per `--project-name`. By using a unique project name per test run (or per CI job), you get complete network and volume isolation between concurrent executions on the same host.

Key properties:
- **Deterministic versions**: pin images (`postgres:16.3-alpine`) so the database you test against matches production.
- **Health checks**: `depends_on: condition: service_healthy` blocks your test runner until every service is ready — no `sleep 5` hacks.
- **Profile-gated services**: `profiles: [full]` lets you bring up only the services a given test suite needs.
- **`--env-file` injection**: per-environment overrides (ports, passwords) stay outside the compose file.
- **`--abort-on-container-exit`**: compose exits as soon as the short-lived test-runner container finishes, giving you the correct exit code.

This is distinct from Testcontainers (which starts containers imperatively from test code). Docker Compose is better when:
- The stack has many services (Postgres, Redis, OpenSearch, a fake SMTP server).
- You want service-level health checks composable in one place.
- Non-Node runtimes (Go, Python, Rust) need the same services — one compose file, any language's test runner.

## Compose File Design

### Base Compose File

```yaml
# compose.test.yml
services:
  postgres:
    image: postgres:16.3-alpine
    environment:
      POSTGRES_DB: testdb
      POSTGRES_USER: testuser
      POSTGRES_PASSWORD: testpass
    ports:
      # Use a random host port to avoid collisions when running jobs in parallel
      - "127.0.0.1::5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U testuser -d testdb"]
      interval: 2s
      timeout: 5s
      retries: 15
      start_period: 5s
    tmpfs:
      # Store Postgres data in RAM — dramatically faster for tests
      - /var/lib/postgresql/data:mode=1777

  redis:
    image: redis:7.2-alpine
    ports:
      - "127.0.0.1::6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 1s
      timeout: 3s
      retries: 20

  mailpit:
    # Fake SMTP server with HTTP API — no real emails sent
    image: axllent/mailpit:v1.19
    ports:
      - "127.0.0.1::1025"   # SMTP
      - "127.0.0.1::8025"   # HTTP API / web UI
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8025/api/v1/info"]
      interval: 2s
      timeout: 5s
      retries: 10

  opensearch:
    image: opensearchproject/opensearch:2.14.0
    environment:
      - discovery.type=single-node
      - DISABLE_SECURITY_PLUGIN=true
      - OPENSEARCH_JAVA_OPTS=-Xms256m -Xmx256m
    ports:
      - "127.0.0.1::9200"
    healthcheck:
      test: ["CMD-SHELL", "curl -s http://localhost:9200/_cluster/health | grep -qE '\"status\":\"(green|yellow)\"'"]
      interval: 5s
      timeout: 10s
      retries: 20
      start_period: 30s
    profiles:
      - search

networks:
  default:
    driver: bridge
```

### Getting Dynamic Ports into Your Tests

```bash
# After `docker compose up`, read the dynamically assigned host port:
docker compose -p "$PROJECT" port postgres 5432
# outputs: 127.0.0.1:54321
```

Wrap this in a helper script:

```bash
#!/usr/bin/env bash
# scripts/test-env.sh
set -euo pipefail

PROJECT="${CI_JOB_ID:-$(openssl rand -hex 4)}"
COMPOSE_FILE="compose.test.yml"

start() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --wait
  POSTGRES_PORT=$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" port postgres 5432 | cut -d: -f2)
  REDIS_PORT=$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" port redis 6379 | cut -d: -f2)
  SMTP_PORT=$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" port mailpit 1025 | cut -d: -f2)
  MAILPIT_API_PORT=$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" port mailpit 8025 | cut -d: -f2)

  # Export for the test runner
  export DATABASE_URL="postgresql://testuser:testpass@127.0.0.1:${POSTGRES_PORT}/testdb"
  export REDIS_URL="redis://127.0.0.1:${REDIS_PORT}"
  export SMTP_HOST="127.0.0.1"
  export SMTP_PORT
  export MAILPIT_API="http://127.0.0.1:${MAILPIT_API_PORT}"
  export TEST_PROJECT="$PROJECT"
}

stop() {
  docker compose -p "$TEST_PROJECT" -f "$COMPOSE_FILE" down -v --remove-orphans
}

"$@"
```

### Vitest globalSetup Integration

```typescript
// vitest.integration.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['src/**/*.integration.test.ts'],
    globalSetup: ['./tests/setup/docker-compose-setup.ts'],
    // Run integration tests serially — they share the compose stack
    pool: 'forks',
    poolOptions: { forks: { singleFork: true } },
    testTimeout: 30_000,
  },
});
```

```typescript
// tests/setup/docker-compose-setup.ts
import { execSync, spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';

let project: string;

export async function setup() {
  project = `vitest-${randomBytes(4).toString('hex')}`;
  process.env.TEST_PROJECT = project;

  execSync(
    `docker compose -p ${project} -f compose.test.yml up -d --wait`,
    { stdio: 'inherit' }
  );

  // Resolve dynamic ports and inject into process.env
  const pg = execSync(`docker compose -p ${project} -f compose.test.yml port postgres 5432`)
    .toString().trim().split(':')[1];
  const redis = execSync(`docker compose -p ${project} -f compose.test.yml port redis 6379`)
    .toString().trim().split(':')[1];

  process.env.DATABASE_URL = `postgresql://testuser:testpass@127.0.0.1:${pg}/testdb`;
  process.env.REDIS_URL = `redis://127.0.0.1:${redis}`;

  // Run migrations against the fresh database
  execSync('npx drizzle-kit migrate', {
    env: { ...process.env },
    stdio: 'inherit',
  });
}

export async function teardown() {
  if (project) {
    execSync(
      `docker compose -p ${project} -f compose.test.yml down -v --remove-orphans`,
      { stdio: 'inherit' }
    );
  }
}
```

## CI Configuration (GitHub Actions)

```yaml
# .github/workflows/integration.yml
jobs:
  integration-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        shard: [1, 2, 3]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci

      # Each matrix shard gets its own project name via GITHUB_JOB + matrix index
      - name: Run integration tests (shard ${{ matrix.shard }}/3)
        env:
          # CI_JOB_ID is used by test-env.sh to name the project
          CI_JOB_ID: "ci-${{ github.run_id }}-${{ matrix.shard }}"
        run: |
          source <(./scripts/test-env.sh start)
          trap './scripts/test-env.sh stop' EXIT
          npx vitest run --config vitest.integration.config.ts \
            --shard=${{ matrix.shard }}/3
```

## Database Isolation Between Test Files

When multiple test files share one Postgres container, use a separate schema per file to prevent row-level cross-contamination:

```typescript
// tests/helpers/isolated-schema.ts
import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import { randomBytes } from 'node:crypto';
import * as schema from '../../src/db/schema';

export async function createIsolatedSchema() {
  const schemaName = `test_${randomBytes(6).toString('hex')}`;
  const client = postgres(process.env.DATABASE_URL!);
  const db = drizzle(client, { schema });

  await client`CREATE SCHEMA ${client(schemaName)}`;
  await client`SET search_path TO ${client(schemaName)}`;

  // Run table DDL scoped to this schema
  // (Drizzle push or raw SQL migration)

  return {
    db,
    cleanup: async () => {
      await client`DROP SCHEMA ${client(schemaName)} CASCADE`;
      await client.end();
    },
  };
}
```

```typescript
// src/users/users.repository.integration.test.ts
import { createIsolatedSchema } from '../helpers/isolated-schema';

let cleanup: () => Promise<void>;
let db: ReturnType<typeof createIsolatedSchema> extends Promise<infer T> ? T['db'] : never;

beforeAll(async () => {
  const result = await createIsolatedSchema();
  db = result.db;
  cleanup = result.cleanup;
});

afterAll(() => cleanup());

test('creates a user and retrieves it by id', async () => {
  const [created] = await db.insert(users).values({ name: 'Alice', email: 'alice@example.com' }).returning();
  const found = await db.query.users.findFirst({ where: eq(users.id, created.id) });
  expect(found?.name).toBe('Alice');
});
```

## Anti-patterns

- **Using `depends_on` without health checks** — `depends_on: service_name` (simple form) only waits for the container to start, not for the service inside it to be ready. Always use `condition: service_healthy` and define a `healthcheck` for every backing service.
- **Hardcoded host ports** — `"5432:5432"` collides when two CI jobs run on the same host. Use `"127.0.0.1::5432"` (double colon) to let Docker pick a free port and query it with `docker compose port`.
- **Not using `tmpfs` for Postgres data** — test databases don't need durability. Mounting `/var/lib/postgresql/data` on `tmpfs` speeds up inserts by 3–10× and eliminates I/O bottlenecks.
- **Running `docker compose down` only on success** — if your test runner crashes, containers keep running. Always register a trap or `POST_COMMAND` to run teardown regardless of exit code.
- **One global compose project shared across all CI jobs** — jobs race to create and delete containers. Use per-job project names.

## Gotchas

- **`--wait` flag (Compose v2.1+)** — `docker compose up -d --wait` blocks until all services with health checks report healthy. Without it you must poll manually. Verify your Docker Compose plugin is v2.1 or later: `docker compose version`.
- **`tmpfs` requires the `--tmpfs` flag or `tmpfs:` key, not just a volume with a tmpfs driver** — use the `tmpfs:` key directly under the service, not `volumes:`.
- **OpenSearch memory requirements** — `vm.max_map_count=262144` must be set on the Linux host (`sysctl -w vm.max_map_count=262144`). GitHub-hosted runners allow this. Self-hosted runners may require the setting at machine provisioning time.
- **Mailpit vs MailHog** — MailHog is no longer maintained. Use Mailpit (`axllent/mailpit`) for the SMTP fake server; it has the same API shape but is actively developed and has a v2 API.
- **`docker compose port` output format** — it returns `HOST:PORT`, not just the port. Always split on `:` and take the last segment.

## Verification

```bash
# Start the stack manually and confirm all services are healthy
docker compose -p mytest -f compose.test.yml up -d --wait
docker compose -p mytest -f compose.test.yml ps

# Confirm dynamic ports work
docker compose -p mytest -f compose.test.yml port postgres 5432

# Run a quick connectivity check
psql "$(./scripts/test-env.sh start && echo $DATABASE_URL)" -c "SELECT 1"

# Confirm teardown removes everything (no orphan volumes)
docker compose -p mytest -f compose.test.yml down -v --remove-orphans
docker volume ls | grep mytest   # should return nothing
```

All services should show `(healthy)` in `docker compose ps` before the test runner starts.

## Related

- `test-containers-docker.md`
- `integration-test-database.md`
- `test-database-isolation.md`
- `transactional-test-rollback.md`
- `github-actions-service-container-integration-tests.md`
- `database-seeding-tests.md`

## Sources

- Docker Compose v2 health checks: https://docs.docker.com/compose/how-tos/startup-order/
- Docker Compose `--wait` flag: https://docs.docker.com/reference/cli/docker/compose/up/
- Drizzle ORM migrations: https://orm.drizzle.team/docs/migrations
- Mailpit documentation: https://mailpit.axllent.org/docs/
- OpenSearch single-node setup: https://opensearch.org/docs/latest/install-and-configure/install-opensearch/docker/
