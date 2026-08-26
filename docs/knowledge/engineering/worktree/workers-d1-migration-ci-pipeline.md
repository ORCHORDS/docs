# Cloudflare D1 Migration CI/CD Pipeline

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
D1 database schema migrations need to run automatically on every deploy, with a rollback mechanism when a migration fails, without blocking the preview environment pipeline for unrelated PRs.

## Context
Cloudflare D1 uses a SQL migration file convention under `migrations/` and exposes `wrangler d1 migrations apply` to run pending migrations against a named database. Unlike traditional databases, D1 does not have a connection URL — it is accessed exclusively through the Workers runtime or `wrangler`. This means migrations must run as a `wrangler` CLI step in CI, not as a standalone Node.js script. The migration state is tracked in a `d1_migrations` table managed by Wrangler inside the D1 database itself.

## Migration File Convention
```sql
-- migrations/0001_create_users.sql
CREATE TABLE IF NOT EXISTS users (
  id         TEXT PRIMARY KEY,
  email      TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- migrations/0002_add_display_name.sql
ALTER TABLE users ADD COLUMN display_name TEXT;

-- migrations/0003_create_sessions.sql
CREATE TABLE IF NOT EXISTS sessions (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
```

## wrangler.toml D1 Binding
```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"
database_name = "my-app-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[env.staging]
[[env.staging.d1_databases]]
binding = "DB"
database_name = "my-app-staging"
database_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
```

## GitHub Actions: Preview Migration (Dry Run)
```yaml
# .github/workflows/d1-preview.yml
name: D1 Migration Preview

on:
  pull_request:
    paths:
      - "migrations/**"
      - "wrangler.toml"

jobs:
  preview-migrations:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Preview pending migrations
        id: preview
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          OUTPUT=$(pnpm wrangler d1 migrations list DB --env staging 2>&1)
          echo "output<<EOF" >> "$GITHUB_OUTPUT"
          echo "$OUTPUT" >> "$GITHUB_OUTPUT"
          echo "EOF" >> "$GITHUB_OUTPUT"

      - name: Post migration plan as PR comment
        uses: actions/github-script@v7
        with:
          script: |
            const output = `${{ steps.preview.outputs.output }}`;
            github.rest.issues.createComment({
              ...context.repo,
              issue_number: context.issue.number,
              body: `## D1 Migration Preview\n\`\`\`\n${output}\n\`\`\``,
            });
```

## GitHub Actions: Apply Migrations on Deploy
```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  migrate-and-deploy:
    runs-on: ubuntu-latest
    environment: production
    concurrency:
      group: production-deploy
      cancel-in-progress: false   # never cancel an in-flight migration
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Apply staging migrations first
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler d1 migrations apply DB --env staging

      - name: Smoke-test staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm vitest run --project=smoke --config vitest.smoke.config.ts

      - name: Apply production migrations
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler d1 migrations apply DB

      - name: Deploy Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler deploy
```

## TypeScript Migration Validator
```typescript
// scripts/validate-migrations.ts
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const MIGRATIONS_DIR = join(process.cwd(), "migrations");

interface MigrationFile {
  index: number;
  name: string;
  filename: string;
}

function parseMigrations(): MigrationFile[] {
  return readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(".sql"))
    .map((filename) => {
      const match = filename.match(/^(\d+)_(.+)\.sql$/);
      if (!match) throw new Error(`Invalid migration filename: ${filename}`);
      return { index: Number(match[1]), name: match[2], filename };
    })
    .sort((a, b) => a.index - b.index);
}

function validateSequential(migrations: MigrationFile[]): void {
  for (let i = 0; i < migrations.length; i++) {
    if (migrations[i].index !== i + 1) {
      throw new Error(
        `Migration sequence gap: expected ${i + 1}, got ${migrations[i].index}`
      );
    }
  }
}

function validateNoDestructiveDDL(migrations: MigrationFile[]): void {
  const dangerous = /\bDROP\s+(TABLE|COLUMN|INDEX)\b/i;
  for (const m of migrations) {
    const sql = readFileSync(join(MIGRATIONS_DIR, m.filename), "utf8");
    if (dangerous.test(sql)) {
      console.warn(`Warning: destructive DDL detected in ${m.filename}`);
    }
  }
}

const migrations = parseMigrations();
validateSequential(migrations);
validateNoDestructiveDDL(migrations);
console.log(`Validated ${migrations.length} migration files — all clear`);
```

## Anti-patterns
- Running `wrangler d1 migrations apply` in parallel against the same database — D1 does not support concurrent DDL, causing partial failures
- Skipping the staging migration step and applying directly to production
- Using `--experimental-local` for production migration checks — local SQLite does not replicate D1's remote behaviour for STRICT tables or generated columns
- Setting `cancel-in-progress: true` on the deploy concurrency group — a cancelled mid-migration leaves the database in a partial state

## Gotchas
- `wrangler d1 migrations apply` is idempotent for already-applied migrations but will error on syntax issues before applying any new migration in the batch
- D1 has a 1 MB SQL statement size limit per migration file — split large seed inserts across multiple files
- The `d1_migrations` tracking table lives in the same D1 database; if the database is deleted and re-created, migration history is lost and all files will re-apply
- Cloudflare API tokens used in CI need the `D1:Edit` permission scoped to the correct account

## Verification
```bash
# List applied migrations for staging environment
pnpm wrangler d1 migrations list DB --env staging

# Verify schema state after applying
pnpm wrangler d1 execute DB --env staging \
  --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"

# Run integration tests against staging D1
pnpm vitest run --project=integration
```

## Related
- `/documentation/docs/policies/worktree/wrangler-environments-staging-production.md`
- `/documentation/docs/policies/worktree/github-actions-wrangler-deploy-pipeline.md`
- `/documentation/docs/policies/worktree/workers-kv-r2-d1-storage-selection.md`
- `/documentation/docs/policies/worktree/rollback-strategy.md`
- `/documentation/docs/policies/worktree/trunk-based-development-cloudflare-workers.md`

## Sources
- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://developers.cloudflare.com/d1/platform/limits/
