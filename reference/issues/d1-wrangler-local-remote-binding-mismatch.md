# Local D1 Data Not Matching Remote: wrangler dev Uses Local SQLite by Default

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You run `wrangler dev` and query your D1 database, but the results are empty or stale compared to what the deployed Worker returns. Alternatively, you seed data locally and it never appears in your deployed environment.

Common error messages or confusing behavior:

```
# Local dev returns empty table
GET /users => []

# But remote Cloudflare D1 has 1000 rows
curl https://my-worker.example.com/users => [{"id":1,...}, ...]

# Or: local migration was applied, remote was not, causing:
# Remote: SqliteError: no such column: created_at
```

Developers expect `wrangler dev` to talk to the same D1 database as production — it does not.

---

## Context

- **Runtime**: Cloudflare Workers + D1 (SQLite)
- **Tool**: Wrangler 3.x (`wrangler dev`, `wrangler d1 execute`)
- **Database**: Cloudflare D1 (serverless SQLite)
- **Pattern**: Local development, integration testing, seeding scripts
- **wrangler.toml** D1 binding configured correctly

---

## Root Cause

By design, `wrangler dev` runs against a **local SQLite file** stored in `.wrangler/state/v3/d1/` — not against your Cloudflare-hosted D1 database. This is a deliberate decision to enable offline development and avoid mutating production data during iteration.

The local SQLite database is a completely independent file. It shares the same binding name as your remote D1 database, but:

1. It starts empty on first run.
2. Migrations applied via `wrangler d1 execute --local` only affect it.
3. Seed data inserted locally stays local.
4. Remote migrations and data are invisible to the local dev server.

The `--remote` flag overrides this behavior and proxies D1 queries to the actual Cloudflare D1 API, but this uses real network requests and counts against your D1 read/write limits.

**Local database location**:
```
.wrangler/state/v3/d1/<database-id>/db.sqlite
```

**Remote database**: Cloudflare edge, accessed via D1 HTTP API.

---

## Broken Code

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { results } = await env.DB.prepare(
      'SELECT * FROM users LIMIT 10'
    ).all();

    // Returns empty array in local dev even though remote has data
    return Response.json(results);
  },
};

interface Env {
  DB: D1Database;
}
```

```bash
# Developer applies migration to remote only:
npx wrangler d1 execute my-app-db --file=./migrations/0001_add_users.sql

# But forgets to apply locally, so local dev crashes:
npx wrangler dev
curl http://localhost:8787/users
# => SqliteError: no such table: users
```

```bash
# Developer seeds local data:
npx wrangler d1 execute my-app-db --local --command="INSERT INTO users VALUES (1,'Alice')"

# Deploys and tests remote — data missing:
npx wrangler deploy
curl https://my-worker.example.com/users
# => []
```

---

## Fix

### Option 1 — Use `--remote` flag for dev against real D1

```bash
# Runs wrangler dev but proxies D1 calls to Cloudflare edge
npx wrangler dev --remote

# Now local code talks to the real D1 database
curl http://localhost:8787/users
# => [{"id":1,"name":"Alice"}, ...]
```

> Warning: `--remote` uses real D1 quota and can mutate production data. Use a separate staging D1 database for safer remote dev.

### Option 2 — Maintain a seed script applied to both environments

```bash
# migrations/seed.sql
INSERT OR IGNORE INTO users (id, name, email) VALUES
  (1, 'Alice', 'alice@example.com'),
  (2, 'Bob',   'bob@example.com');
```

```bash
# Apply migration + seed to LOCAL:
npx wrangler d1 execute my-app-db --local --file=./migrations/0001_create_users.sql
npx wrangler d1 execute my-app-db --local --file=./migrations/seed.sql

# Apply migration to REMOTE (not seed — use real data or a CI seed step):
npx wrangler d1 execute my-app-db --file=./migrations/0001_create_users.sql
```

### Option 3 — Use a dedicated staging D1 database

```toml
# wrangler.toml — production binding
[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "prod-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

```toml
# wrangler.staging.toml — staging overlay
[[d1_databases]]
binding = "DB"
database_name = "my-app-db-staging"
database_id = "stg-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

```bash
# Dev against staging remote D1 — separate from production
npx wrangler dev --remote --config wrangler.staging.toml
```

### Option 4 — Automate migration parity with a Makefile

```makefile
# Makefile
.PHONY: migrate-local migrate-remote migrate-all

MIGRATION_DIR := ./migrations
DB_NAME       := my-app-db

migrate-local:
    @for f in $(MIGRATION_DIR)/*.sql; do \
      echo "Applying $$f locally..."; \
      npx wrangler d1 execute $(DB_NAME) --local --file=$$f; \
    done

migrate-remote:
    @for f in $(MIGRATION_DIR)/*.sql; do \
      echo "Applying $$f remotely..."; \
      npx wrangler d1 execute $(DB_NAME) --file=$$f; \
    done

migrate-all: migrate-local migrate-remote
```

```bash
# Apply all migrations everywhere:
make migrate-all

# Then start dev:
npx wrangler dev
```

### Option 5 — Inspect the local SQLite file directly

```bash
# Find the local D1 file
ls .wrangler/state/v3/d1/

# Open with sqlite3 for direct inspection
sqlite3 .wrangler/state/v3/d1/<database-id>/db.sqlite '.tables'
sqlite3 .wrangler/state/v3/d1/<database-id>/db.sqlite 'SELECT COUNT(*) FROM users;'

# Or use the wrangler CLI
npx wrangler d1 execute my-app-db --local --command='SELECT COUNT(*) FROM users;'
```

---

## Verification

```bash
# 1. Check local D1 state
npx wrangler d1 execute my-app-db --local --command='SELECT name FROM sqlite_master WHERE type="table";'

# 2. Check remote D1 state
npx wrangler d1 execute my-app-db --command='SELECT name FROM sqlite_master WHERE type="table";'

# 3. Compare row counts
npx wrangler d1 execute my-app-db --local --command='SELECT COUNT(*) FROM users;'
npx wrangler d1 execute my-app-db --command='SELECT COUNT(*) FROM users;'

# 4. Run dev in remote mode and confirm data matches
npx wrangler dev --remote &
curl http://localhost:8787/users | jq 'length'
# Should match remote count

# 5. Run dev in local mode and confirm seed was applied
npx wrangler dev &
curl http://localhost:8787/users | jq 'length'
# Should match seeded row count
```

---

## Anti-patterns

- Running `wrangler dev` (without `--remote`) and assuming it reads production data.
- Seeding local D1 and deploying without seeding remote, then wondering why remote is empty.
- Applying migrations to remote only and never updating the local SQLite file.
- Committing `.wrangler/state/` to git — it is ephemeral dev state, not source-of-truth.
- Using `--remote` in CI tests against the production D1 database (risk of data corruption).

---

## Gotchas

- `.wrangler/state/` is created fresh per environment — deleting it resets local D1 to empty.
- `wrangler d1 migrations apply` (D1 migrations API, GA as of 2024) handles migration tracking; prefer it over manual `--file` loops.
- The `--local` flag on `wrangler d1 execute` is separate from `wrangler dev --local` (the latter is the default); both target the same `.wrangler/state/` SQLite.
- D1 in `--remote` mode during `wrangler dev` still runs your Worker code locally — only D1 reads/writes go to Cloudflare.
- `wrangler d1 export` can dump a remote D1 to a SQL file for local import, useful for production-parity dev.

---

## Related

- `documentation/categories/issues/workers-kv-binding-undefined-wrangler-toml.md`
- `documentation/categories/issues/workers-fetch-null-body-consumed-error.md`
- `documentation/categories/issues/workers-durable-object-id-from-name-cross-script.md`

---

## Sources

- https://developers.cloudflare.com/d1/get-started/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://developers.cloudflare.com/d1/best-practices/local-development/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/wrangler/configuration/#d1-databases
