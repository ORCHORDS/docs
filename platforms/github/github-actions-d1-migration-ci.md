# GitHub Actions D1 Migration CI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Cloudflare D1 database schema drifts out of sync with your Workers application because migrations are applied manually or forgotten before deploy. You need an automated CI/CD pipeline that applies D1 migrations before every production deployment, validates them on pull requests, and backs up the database first.

---

## Context
Cloudflare D1 uses Wrangler's migration system (`wrangler d1 migrations apply`) to evolve your SQLite-compatible database schema. When deploying via GitHub Actions, running migrations as a pre-deploy step ensures the schema is always consistent with the Worker code being deployed. The `--dry-run` flag lets PRs validate migration SQL without touching the database. Exporting a backup with `wrangler d1 export` before applying provides a rollback point. The `wrangler d1 migrations list` command lets you inspect which migrations have been applied vs. pending, making status checks easy to automate.

---

## Setup / Config

```yaml
# wrangler.toml — D1 binding configuration
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
migrations_dir = "migrations"
```

```yaml
# .github/workflows/deploy.yml — full workflow
name: Deploy Worker

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
  DATABASE_NAME: my-app-db

jobs:
  migrate-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci
```

---

## Implementation

```yaml
      # 1. Check pending migrations before doing anything
      - name: List migration status
        run: |
          npx wrangler d1 migrations list $DATABASE_NAME --env production

      # 2. On PRs: dry-run only — validate SQL without applying
      - name: Dry-run migrations (PR only)
        if: github.event_name == 'pull_request'
        run: |
          npx wrangler d1 migrations apply $DATABASE_NAME \
            --env production \
            --dry-run

      # 3. On main: back up then apply
      - name: Backup D1 database before migration
        if: github.ref == 'refs/heads/main'
        run: |
          TIMESTAMP=$(date +%Y%m%dT%H%M%S)
          npx wrangler d1 export $DATABASE_NAME \
            --env production \
            --output "backups/db-$TIMESTAMP.sql"
          echo "Backup written to backups/db-$TIMESTAMP.sql"

      - name: Apply D1 migrations
        if: github.ref == 'refs/heads/main'
        run: |
          npx wrangler d1 migrations apply $DATABASE_NAME \
            --env production

      # 4. Deploy Worker after migrations succeed
      - name: Deploy Worker
        if: github.ref == 'refs/heads/main'
        run: npx wrangler deploy --env production
```

---

## Integration / Testing

```bash
# Locally: list which migrations are pending
npx wrangler d1 migrations list my-app-db --env production

# Locally: dry-run to validate migration SQL
npx wrangler d1 migrations apply my-app-db --env production --dry-run

# Locally: export a backup before applying
npx wrangler d1 export my-app-db --env production --output backup.sql

# Locally: apply migrations
npx wrangler d1 migrations apply my-app-db --env production

# Verify applied migrations in D1 internal table
npx wrangler d1 execute my-app-db \
  --env production \
  --command "SELECT * FROM d1_migrations ORDER BY applied_at DESC LIMIT 10;"

# Check the Worker deployed successfully
curl -s https://my-worker.my-subdomain.workers.dev/healthz
```

---

## Anti-patterns
- **Applying migrations after deploy** — The Worker code and schema are momentarily out of sync, causing runtime errors for in-flight requests. Always migrate first.
- **Skipping `--dry-run` on PRs** — Syntax errors in migration SQL only surface at deploy time, too late to catch in review. Dry-run in CI catches them early.
- **No backup step** — If a migration is destructive and wrong, without a backup you have no rollback path. Always export before applying in production.
- **Hardcoding `database_id` in env vars** — The ID already lives in `wrangler.toml`; duplicating it in secrets creates drift. Reference the binding name instead.
- **Running migrations inside the Worker at startup** — D1 migration apply is a Wrangler CLI concern, not runtime Worker logic. Don't embed migration logic in Worker code.

---

## Gotchas
- `wrangler d1 export` requires the D1 database to not be under heavy write load; schedule backups during low-traffic windows if possible.
- The `--dry-run` flag validates SQL syntax but does not catch semantic errors like referencing a column that doesn't exist in the current schema.
- `wrangler d1 migrations apply` is idempotent for already-applied migrations; it tracks state in a `d1_migrations` table automatically created in your database.
- `CLOUDFLARE_API_TOKEN` must have D1 Edit and Workers Deploy permissions; a token with only Workers Deploy will fail on migration steps.
- Migration files must be sequentially numbered (e.g., `0001_create_users.sql`) and reside in the directory specified by `migrations_dir` in `wrangler.toml`.

---

## Verification

```bash
# Confirm the d1_migrations tracking table exists and has rows
npx wrangler d1 execute my-app-db \
  --env production \
  --command "SELECT name, applied_at FROM d1_migrations;"

# Confirm migration list shows all as applied
npx wrangler d1 migrations list my-app-db --env production
# Expected output: all migration files listed with an applied timestamp

# Confirm Worker reflects schema changes (example: new column exists)
npx wrangler d1 execute my-app-db \
  --env production \
  --command "PRAGMA table_info(users);"
```

---

## Related
- `cloudflare-d1-migrations-wrangler.md`
- `github-required-status-checks-workers-ci.md`
- `wrangler-deploy-env-production.md`

---

## Sources
- Cloudflare D1 Migrations Docs — https://developers.cloudflare.com/d1/reference/migrations/
- Wrangler CLI D1 Commands — https://developers.cloudflare.com/workers/wrangler/commands/#d1
- GitHub Actions `actions/cache` — https://github.com/actions/cache
