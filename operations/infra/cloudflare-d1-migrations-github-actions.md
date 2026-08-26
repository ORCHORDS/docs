# Cloudflare D1 Schema Migrations via GitHub Actions

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your D1 database schema evolves with application code. Running `wrangler d1 execute` manually is
error-prone and cannot be audited. You need a repeatable, zero-downtime migration pipeline that
applies numbered SQL migrations to both staging and production D1 databases as part of your CI/CD
workflow, with rollback capability and migration state tracking.

## Context

Cloudflare D1 does not have a built-in migration runner. The common approach is:

1. Keep numbered SQL files in a `migrations/` directory.
2. Track applied migrations in a `_migrations` table inside D1 itself.
3. Run `wrangler d1 execute` inside GitHub Actions, scoped to the relevant environment database.

Wrangler 3+ supports `--file` to execute a SQL file and `--command` for inline SQL. The `--local`
flag targets a local SQLite replica; omit it to hit the remote D1 database. Migration state must be
idempotent: re-running an already-applied migration must be a no-op or produce an explicit skip.

D1 does not support multi-statement transactions across DDL and DML in a single `execute` call in all
situations — each migration file should be self-contained and atomic where possible.

## Migration File Convention

```
migrations/
  0001_initial_schema.sql
  0002_add_sessions_table.sql
  0003_add_org_slug_index.sql
  0004_events_backfill_nullable.sql
```

```sql
-- migrations/0001_initial_schema.sql
-- Description: initial schema
CREATE TABLE IF NOT EXISTS users (
  id        TEXT PRIMARY KEY,
  email     TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS orgs (
  id         TEXT PRIMARY KEY,
  slug       TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
```

```sql
-- migrations/0002_add_sessions_table.sql
-- Description: user sessions
CREATE TABLE IF NOT EXISTS sessions (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
```

## Migration Runner Script (TypeScript / Node)

```typescript
// scripts/migrate.ts  – run with: npx tsx scripts/migrate.ts
import { execSync } from "child_process";
import { readdirSync, readFileSync } from "fs";
import path from "path";

const MIGRATIONS_DIR = path.resolve("migrations");
const DB_NAME        = process.env.D1_DB_NAME  ?? "orchords-db";
const ENV_FLAG       = process.env.CF_ENV === "production" ? "--env production" : "";

function wrangler(sql: string): string {
  return execSync(
    `npx wrangler d1 execute ${DB_NAME} ${ENV_FLAG} --command "${sql.replace(/"/g, '\\"')}" --json`,
    { encoding: "utf8" },
  );
}

function wranglerFile(file: string): void {
  execSync(
    `npx wrangler d1 execute ${DB_NAME} ${ENV_FLAG} --file "${file}"`,
    { stdio: "inherit" },
  );
}

async function main(): Promise<void> {
  // Ensure migration tracking table exists
  wrangler(
    "CREATE TABLE IF NOT EXISTS _migrations (id TEXT PRIMARY KEY, applied_at INTEGER NOT NULL DEFAULT (unixepoch()))",
  );

  const applied: Set<string> = new Set(
    JSON.parse(wrangler("SELECT id FROM _migrations ORDER BY id"))
      .map((r: { id: string }) => r.id),
  );

  const files = readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(".sql"))
    .sort();

  for (const file of files) {
    if (applied.has(file)) {
      console.log(`  SKIP  ${file} (already applied)`);
      continue;
    }
    console.log(`  APPLY ${file}`);
    wranglerFile(path.join(MIGRATIONS_DIR, file));
    wrangler(`INSERT INTO _migrations (id) VALUES ("${file}")`);
    console.log(`  DONE  ${file}`);
  }

  console.log("Migration complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

## GitHub Actions Pipeline

```yaml
# .github/workflows/db-migrate.yml
name: D1 Database Migrations

on:
  push:
    branches: [main, staging]
    paths:
      - "migrations/**"
      - "scripts/migrate.ts"

jobs:
  migrate-staging:
    if: github.ref == 'refs/heads/staging'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci
      - name: Run migrations (staging)
        run: npx tsx scripts/migrate.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          D1_DB_NAME: orchords-db-staging
          CF_ENV: staging

  migrate-production:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production        # requires manual approval in GitHub Environments
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci
      - name: Run migrations (production)
        run: npx tsx scripts/migrate.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          D1_DB_NAME: orchords-db-production
          CF_ENV: production
```

## Rollback Migration Pattern

```sql
-- migrations/0005_drop_legacy_events.sql
-- Description: drop legacy events table (rollback: 0005_rollback_drop_legacy_events.sql)
DROP TABLE IF EXISTS legacy_events;
```

```typescript
// scripts/rollback.ts – revert the last N migrations
import { execSync } from "child_process";

const DB_NAME  = process.env.D1_DB_NAME ?? "orchords-db";
const ENV_FLAG = process.env.CF_ENV === "production" ? "--env production" : "";
const STEPS    = parseInt(process.env.ROLLBACK_STEPS ?? "1", 10);

function wrangler(sql: string): string {
  return execSync(
    `npx wrangler d1 execute ${DB_NAME} ${ENV_FLAG} --command "${sql}" --json`,
    { encoding: "utf8" },
  );
}

async function main(): Promise<void> {
  const rows: Array<{ id: string }> = JSON.parse(
    wrangler(`SELECT id FROM _migrations ORDER BY id DESC LIMIT ${STEPS}`),
  );
  for (const { id } of rows) {
    const rollbackFile = id.replace(".sql", "_rollback.sql");
    console.log(`  ROLLBACK ${id} via ${rollbackFile}`);
    execSync(
      `npx wrangler d1 execute ${DB_NAME} ${ENV_FLAG} --file "migrations/${rollbackFile}"`,
      { stdio: "inherit" },
    );
    wrangler(`DELETE FROM _migrations WHERE id = "${id}"`);
    console.log(`  DONE rollback ${id}`);
  }
}

main().catch((err) => { console.error(err); process.exit(1); });
```

## Terraform: D1 Database Provisioning

```hcl
# terraform/cloudflare-d1.tf
resource "cloudflare_d1_database" "app_staging" {
  account_id = var.cloudflare_account_id
  name       = "orchords-db-staging"
}

resource "cloudflare_d1_database" "app_production" {
  account_id = var.cloudflare_account_id
  name       = "orchords-db-production"
}

output "d1_staging_id"    { value = cloudflare_d1_database.app_staging.id }
output "d1_production_id" { value = cloudflare_d1_database.app_production.id }
```

```hcl
# wrangler.toml binding (generated or maintained alongside Terraform outputs)
[[d1_databases]]
binding  = "DB"
database_name = "orchords-db-production"
database_id   = "abc123..."   # from terraform output d1_production_id
```

## Anti-patterns

- **Mutating migrations retroactively**: once a migration file is committed and applied, modifying
  its SQL breaks the hash/name-based idempotency check; always create a new numbered file.
- **DDL inside transactions via Workers runtime**: D1's Workers binding does not support DDL inside
  explicit `BEGIN`/`COMMIT` blocks in all versions; run schema migrations through `wrangler d1
  execute`, not from within application Workers code.
- **No approval gate on production**: always use a GitHub Environment with `required_reviewers` for
  production migration jobs to prevent accidental destructive DDL.
- **Running migrations and deploys in parallel**: deploy the new Worker code only after migrations
  complete; reversed order causes missing-column errors.

## Gotchas

- `wrangler d1 execute --file` silently ignores SQL comment lines starting with `--` but may fail
  on certain multi-statement files depending on Wrangler version; test locally with `--local` first.
- D1 is SQLite under the hood — `ALTER TABLE` support is limited; use shadow table + copy patterns
  for column renames or type changes.
- The `_migrations` table records filenames, not content hashes; renaming a file causes it to be
  re-applied.
- D1 remote execution via Wrangler counts against your D1 read/write unit quota.

## Verification

```bash
# List applied migrations in staging
npx wrangler d1 execute orchords-db-staging \
  --command "SELECT id, datetime(applied_at, 'unixepoch') as ts FROM _migrations ORDER BY id"

# Validate schema in production
npx wrangler d1 execute orchords-db-production \
  --command ".schema" --env production

# Dry-run: show pending migrations without applying
D1_DB_NAME=orchords-db-staging DRY_RUN=1 npx tsx scripts/migrate.ts
```

## Related

- `terraform-cloudflare-provider-workers-d1.md` — Terraform D1 binding configuration
- `pulumi-cloudflare-d1-database-iac.md` — Pulumi D1 provisioning
- `cloudflare-workers-cron-triggers-terraform.md` — scheduled maintenance workers
- `wrangler-toml-multi-environment-config.md` — multi-env wrangler setup
- `disaster-recovery-rto-rpo.md` — backup strategy for D1

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/wrangler-commands/#execute
- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- https://www.sqlite.org/lang_altertable.html
