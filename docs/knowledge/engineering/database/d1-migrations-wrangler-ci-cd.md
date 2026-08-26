# d1-migrations-wrangler-ci-cd

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project schema changes applied locally via `wrangler d1 execute` are
not reflected in the production database after CI/CD deploys the new
Worker code. The Worker deploys but the migration never ran, causing
runtime errors when new code references columns or tables that do not
exist yet in production D1.

Alternatively, a botched manual migration ran in production but is
not tracked anywhere, causing the next automated migration to fail
with "table already exists" or duplicate column errors.

## Context

Cloudflare D1 has built-in migration support via `wrangler d1
migrations`. It stores applied migration state in a
`d1_migrations` table inside the D1 database itself. Migration files
live in a configured directory (default: `migrations/`) and are named
with a numeric prefix so Wrangler applies them in order.

For example project's 133+ Worker routes, schema stability is critical.
Migrations must run _before_ the new Worker code is live, so that
the new code never runs against an old schema. The correct deploy
order is: apply migrations → then deploy Worker.

## Migration File Conventions

```
migrations/
  0001_initial_schema.sql
  0002_add_vote_direction.sql
  0003_communities_table.sql
  0004_add_fk_constraints.sql
  0005_add_analytics_events.sql
```

Rules:
- Zero-padded 4-digit prefix, monotonically increasing.
- One logical change per file; never modify an applied migration.
- Each file must be idempotent or guarded (see below).
- Files are plain SQL; no migration DSL required.

```sql
-- migrations/0005_add_analytics_events.sql
CREATE TABLE IF NOT EXISTS analytics_events (
  id         TEXT PRIMARY KEY,
  type       TEXT NOT NULL,
  ref_id     TEXT,
  ts         INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_type_ts
  ON analytics_events(type, ts);
```

Use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` so
that re-running a migration (e.g. in local dev) does not fail.

## wrangler.toml Configuration

```toml
# wrangler.toml
[[d1_databases]]
binding       = "DB"
database_name = "example project-prod"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
migrations_dir = "migrations"
```

`migrations_dir` tells Wrangler where to find migration files. The
`d1_migrations` tracking table is created automatically in the D1
database on first `wrangler d1 migrations apply` call.

## Applying Migrations Locally

```bash
# Create a new migration file:
wrangler d1 migrations create example project-prod add_analytics_events

# List pending migrations:
wrangler d1 migrations list example project-prod

# Apply all pending migrations to local dev database:
wrangler d1 migrations apply example project-prod --local

# Apply to remote production database:
wrangler d1 migrations apply example project-prod --remote
```

Always apply locally first with `--local` to catch SQL errors before
touching production.

## GitHub Actions CI/CD Pipeline

Apply migrations in CI _before_ deploying the Worker. The Worker
deploy step should be in the same job, running after migrations:

```yaml
# .github/workflows/deploy.yml
name: Deploy example project

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"

      - run: npm ci

      # Step 1: Apply D1 migrations BEFORE Worker deploy
      - name: Apply D1 migrations
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler d1 migrations apply example project-prod --remote

      # Step 2: Deploy Worker AFTER migrations are confirmed applied
      - name: Deploy Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler deploy
```

This guarantees the new schema is live before any Worker instance
starts serving traffic with code that depends on it.

## Migration History Table

Wrangler creates and manages a `d1_migrations` table automatically:

```sql
-- Created by Wrangler in your D1 database:
CREATE TABLE d1_migrations (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT UNIQUE,
  applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

Inspect it to see what has been applied:

```bash
wrangler d1 execute example project-prod \
  --command "SELECT * FROM d1_migrations ORDER BY id;" \
  --remote
```

Example output:

```
 id | name                              | applied_at
----+-----------------------------------+--------------------
  1 | 0001_initial_schema.sql           | 2026-01-15 10:02:33
  2 | 0002_add_vote_direction.sql       | 2026-02-10 14:20:11
  3 | 0003_communities_table.sql        | 2026-03-05 09:45:00
  4 | 0004_add_fk_constraints.sql       | 2026-04-18 11:30:55
  5 | 0005_add_analytics_events.sql     | 2026-08-22 08:12:41
```

## Rollback Strategies

D1 migrations have no built-in "down" migration mechanism. Options:

| Approach               | When to use                               |
|------------------------|-------------------------------------------|
| Write a new migration  | Column/table additions (safest)           |
| Manual SQL via exec    | Fix a botched migration interactively     |
| D1 time travel         | Restore to a point-in-time snapshot       |
| D1 export + reimport   | Nuclear: full restore from SQL dump       |

Recommended: always write an `0006_rollback_analytics_events.sql`
that drops or reverts the change, rather than editing
`0005_add_analytics_events.sql`. Modifying an applied migration causes
a hash mismatch and Wrangler will refuse to manage it.

D1 time travel (point-in-time restore) is available for up to 30 days:

```bash
wrangler d1 time-travel restore example project-prod \
  --timestamp "2026-08-21T10:00:00Z" \
  --remote
```

Use time travel only for data recovery; it reverts _all_ data changes,
not just the problematic migration.

## Anti-Patterns

- Deploying Worker code first and running migrations after—new code
  may start handling requests against the old schema mid-deploy.
- Editing an already-applied migration file—Wrangler detects the
  hash change and marks the migration as modified; subsequent
  `apply` commands may abort or behave unexpectedly.
- Running `wrangler d1 execute` ad-hoc in production without a
  corresponding migration file—the change is untracked and will be
  absent from any restored database.
- Using `DROP TABLE` without first confirming no live Worker code
  references that table.

## Gotchas

- `wrangler d1 migrations apply` exits 0 even when there are no
  pending migrations—always check stdout for "No migrations to apply"
  vs "Applied N migration(s)" in CI logs.
- SQLite has no `DROP COLUMN` support before version 3.35 (2021).
  D1 uses SQLite 3.44+, so `ALTER TABLE posts DROP COLUMN legacy_col`
  works in D1 but not in older SQLite local dev setups.
- Multi-statement migrations separated by semicolons are executed
  sequentially by Wrangler; a failure mid-file leaves partial state.
  Wrap destructive multi-step migrations in `BEGIN; ... COMMIT;`.
- The `--remote` flag requires `CLOUDFLARE_API_TOKEN` and
  `CLOUDFLARE_ACCOUNT_ID` environment variables in CI.

## Verification

```bash
# Confirm migration applied in production after CI run:
wrangler d1 execute example project-prod \
  --command "SELECT name, applied_at FROM d1_migrations ORDER BY id DESC LIMIT 5;" \
  --remote

# Confirm the target table/column exists:
wrangler d1 execute example project-prod \
  --command "PRAGMA table_info(analytics_events);" \
  --remote

# List pending (unapplied) migrations:
wrangler d1 migrations list example project-prod --remote
# Expected output: "No migrations to apply" after a successful CI run.
```

## Related

- `database/d1-foreign-keys-referential-integrity.md`
- `database/postgresql-to-d1-migration-patterns.md`
- `database/backward-compatible-migrations.md`
- `database/migration-rollback-strategy.md`
- `database/database-migration-zero-downtime.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/reference/time-travel/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
