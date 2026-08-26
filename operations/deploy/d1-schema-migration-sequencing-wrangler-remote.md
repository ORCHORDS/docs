# D1 Schema Migration Sequencing with Wrangler Remote

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You are using Cloudflare D1 (the serverless SQLite-compatible database) with Wrangler's built-in migration system. As your schema evolves you need to:

- Apply migrations in guaranteed order across staging and production environments.
- Avoid running the same migration twice (idempotency).
- Coordinate migrations with Worker deploys so code and schema changes are never out of sync.
- Roll back a migration that caused a problem without corrupting the applied-migration log.
- Squash old migrations when the list grows beyond maintainability.

Wrangler's `wrangler d1 migrations apply` command handles some of this, but the rules around ordering, the `d1_migrations` table, and the interaction with Worker deploys are not obvious and trip teams repeatedly.

## Context

Wrangler D1 migrations use a directory of numbered SQL files (`migrations/0001_init.sql`, `migrations/0002_add_users.sql`, …). When you run `wrangler d1 migrations apply`, it:

1. Queries the `d1_migrations` table in your D1 database (created automatically on first apply).
2. Identifies which migration files have not yet been applied (by name).
3. Applies each unapplied migration in filename-sort order inside a transaction.
4. Records each applied migration name in `d1_migrations`.

Key behaviors:
- Migration filenames must sort lexicographically in the order you want them applied. The convention is zero-padded numbers (`0001_`, `0002_`, …).
- `--local` applies to the local D1 SQLite copy used by `wrangler dev`. `--remote` applies to the actual D1 database in your Cloudflare account.
- D1 runs on SQLite semantics, not PostgreSQL. `ALTER TABLE` is limited (no `DROP COLUMN` before SQLite 3.35, no `RENAME COLUMN` before 3.25). Check the D1 SQLite version in the Cloudflare docs.
- Each Worker environment (`staging`, `production`) binds to a different D1 database ID. Migrations must be applied separately to each.

## Step 1 — Directory and naming convention

```
workers/api/
  migrations/
    0001_init.sql
    0002_add_users.sql
    0003_add_sessions.sql
    0004_add_user_email_index.sql
  wrangler.toml
  src/
    index.ts
```

```toml
# workers/api/wrangler.toml

name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[d1_databases]]
binding = "DB"
database_name = "orchords-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # production

[env.staging]
[[env.staging.d1_databases]]
binding = "DB"
database_name = "orchords-staging"
database_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"   # staging
```

## Step 2 — Writing safe D1 migrations

D1 runs each migration file in a single SQLite transaction (with autocommit disabled). A syntax error mid-file rolls back the entire file.

```sql
-- migrations/0002_add_users.sql
-- Use IF NOT EXISTS guards to make migrations idempotent against partial retries

CREATE TABLE IF NOT EXISTS users (
  id       TEXT PRIMARY KEY,
  email    TEXT NOT NULL UNIQUE,
  created  INTEGER NOT NULL  -- Unix epoch seconds
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
```

For destructive changes, use a separate migration file:

```sql
-- migrations/0005_rename_user_name.sql
-- SQLite >= 3.25 supports RENAME COLUMN; check D1's supported version

ALTER TABLE users RENAME COLUMN legacy_name TO display_name;
```

For column drops (if D1's SQLite version supports it):

```sql
-- migrations/0006_drop_legacy_column.sql
ALTER TABLE users DROP COLUMN legacy_status;
```

If the D1 SQLite version does not support `DROP COLUMN`, use the copy-rename pattern:

```sql
-- migrations/0006_drop_legacy_column.sql
-- SQLite copy-rename workaround for older versions without DROP COLUMN support

CREATE TABLE users_new (
  id           TEXT PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  display_name TEXT,
  created      INTEGER NOT NULL
);

INSERT INTO users_new (id, email, display_name, created)
SELECT id, email, display_name, created FROM users;

DROP TABLE users;

ALTER TABLE users_new RENAME TO users;

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
```

## Step 3 — Listing and checking pending migrations

```bash
# List all migrations and their applied status (staging)
npx wrangler d1 migrations list orchords-staging --env staging

# List pending (unapplied) migrations only
npx wrangler d1 migrations list orchords-prod --remote 2>&1 | grep "Not applied"

# Check which migrations are applied without running them
npx wrangler d1 execute orchords-prod --remote \
  --command "SELECT * FROM d1_migrations ORDER BY applied_at ASC;"
```

Sample output of `migrations list`:

```
Migrations to be applied:
┌───────────────────────────────────────┬───────────────┐
│ Name                                  │ Status        │
├───────────────────────────────────────┼───────────────┤
│ 0001_init.sql                         │ applied       │
│ 0002_add_users.sql                    │ applied       │
│ 0003_add_sessions.sql                 │ applied       │
│ 0004_add_user_email_index.sql         │ applied       │
│ 0005_rename_user_name.sql             │ Not applied   │
└───────────────────────────────────────┴───────────────┘
```

## Step 4 — GitHub Actions pipeline: migration before Worker deploy

The critical constraint: **apply migrations before deploying the new Worker code that depends on them**. A Worker that tries to SELECT from a column that does not yet exist returns a 500.

```yaml
# .github/workflows/deploy-with-migration.yml
name: Deploy Worker with D1 Migrations

on:
  push:
    branches: [main]
    paths:
      - "workers/api/**"

jobs:
  apply-migrations-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci

      - name: Preview pending migrations (dry run)
        working-directory: workers/api
        run: npx wrangler d1 migrations list orchords-staging --env staging --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Apply migrations to staging
        working-directory: workers/api
        run: npx wrangler d1 migrations apply orchords-staging --env staging --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy Worker to staging
        working-directory: workers/api
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Smoke test staging
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            "https://orchords-api.staging.workers.dev/api/health")
          [ "$STATUS" = "200" ] || (echo "Staging smoke test failed: $STATUS" && exit 1)

  apply-migrations-production:
    runs-on: ubuntu-latest
    needs: apply-migrations-staging
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci

      - name: Preview pending migrations (production)
        working-directory: workers/api
        run: npx wrangler d1 migrations list orchords-prod --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Apply migrations to production
        working-directory: workers/api
        run: npx wrangler d1 migrations apply orchords-prod --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy Worker to production
        working-directory: workers/api
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Production smoke test
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            "https://api.orchords.workers.dev/api/health")
          [ "$STATUS" = "200" ] || (echo "Production smoke test failed: $STATUS" && exit 1)
```

## Step 5 — Migration rollback

D1 does not have a built-in `wrangler d1 migrations rollback` command. Rollback requires a new migration file that undoes the change.

```sql
-- migrations/0005_rollback_rename_user_name.sql
-- Undo the rename: display_name → legacy_name

ALTER TABLE users RENAME COLUMN display_name TO legacy_name;
```

Apply and deploy in the usual order:

```bash
npx wrangler d1 migrations apply orchords-prod --remote
npx wrangler rollback --name orchords-api --env production
```

For the Worker rollback, use Wrangler Worker Versions to revert the script to the previous version. The migration rollback file stays in the repo permanently as part of the migration history.

## Step 6 — Migration squashing for long-lived projects

After many migrations, the sequential apply time and file count become unwieldy. Squash by:

1. Creating a new `0000_schema_baseline.sql` that represents the full current schema.
2. Deleting all old migration files from the repo.
3. Manually inserting the old migration names into `d1_migrations` in the production database so Wrangler does not try to re-apply them.

```bash
# Insert old migration records so Wrangler skips them
npx wrangler d1 execute orchords-prod --remote --command "
  INSERT OR IGNORE INTO d1_migrations (name, applied_at)
  VALUES
    ('0001_init.sql', strftime('%s', 'now')),
    ('0002_add_users.sql', strftime('%s', 'now')),
    ('0003_add_sessions.sql', strftime('%s', 'now')),
    ('0004_add_user_email_index.sql', strftime('%s', 'now'));
"
```

Only run this on databases that already have those migrations applied. For fresh environments (e.g., a new PR preview D1 database), run the baseline file directly and skip the old names by inserting them.

## Anti-patterns

- **Deploying the Worker before running migrations**: The new code references columns or tables that don't exist yet. Even a 10-second window causes 500s.
- **Writing destructive migrations without a rollback migration**: `DROP TABLE` or `DROP COLUMN` is irreversible without a rollback file planned in advance.
- **Using `--local` flag in production CI jobs**: `--local` applies to the local SQLite file only. Always pass `--remote` in CI.
- **Manually editing `d1_migrations` to skip a bad migration**: Wrangler trusts `d1_migrations` implicitly. Manual edits can leave the schema and migration log out of sync.
- **Running `wrangler d1 execute` with raw DDL instead of the migration system**: Bypasses the `d1_migrations` log entirely. The next `migrations apply` will try to re-apply every pending file including ones that partially succeeded.
- **Sharing a D1 database between staging and production environments**: Always use separate databases per environment. Shared databases mean staging migrations run against production data.

## Gotchas

- D1 `migrations apply` wraps each file in a transaction, but `wrangler d1 execute --file` with a multi-statement file does **not** wrap in a transaction unless you add `BEGIN;` / `COMMIT;` manually.
- D1's SQLite version is updated by Cloudflare and may change between your testing and production apply. Always check the changelog before relying on newer SQLite features.
- Very large migration files (thousands of rows inserted as seed data) may hit D1's per-request CPU time limits. Break large seed migrations into smaller files or use D1's `--batch-size` flag if available.
- The `database_name` in `wrangler.toml` is a human-readable label; `database_id` is the authoritative identifier. If you rename the database in the dashboard, update `database_name` in `wrangler.toml` but the `database_id` remains the binding anchor.
- D1 migrations applied via `wrangler d1 migrations apply` are scoped to the environment specified. Running without `--env` targets the default (root-level) bindings — accidentally running against production when you meant staging is the most common D1 migration incident.

## Verification

```bash
# Confirm all migrations applied in both environments
npx wrangler d1 execute orchords-prod --remote \
  --command "SELECT name, applied_at FROM d1_migrations ORDER BY applied_at;"

npx wrangler d1 execute orchords-staging --env staging --remote \
  --command "SELECT name, applied_at FROM d1_migrations ORDER BY applied_at;"

# Verify schema matches expected shape
npx wrangler d1 execute orchords-prod --remote \
  --command "PRAGMA table_info(users);"

# Count rows to confirm seed data or check no data was lost
npx wrangler d1 execute orchords-prod --remote \
  --command "SELECT COUNT(*) FROM users;"
```

## Related

- `zero-downtime-database-migrations.md`
- `database-migration-deploy-strategy.md`
- `database-migration-rollback-strategies.md`
- `blue-green-deploy-cloudflare-workers.md`
- `blue-green-database-cutover.md`
- `pre-deploy-database-backup.md`
- `rollback-strategies-workers-pages.md`

## Sources

- Wrangler D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
- D1 `wrangler.toml` configuration: https://developers.cloudflare.com/d1/get-started/
- D1 SQLite compatibility: https://developers.cloudflare.com/d1/platform/client-api/
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
