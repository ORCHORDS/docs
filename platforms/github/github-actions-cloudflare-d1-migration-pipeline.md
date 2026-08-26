# GitHub Actions CI Pipeline for Cloudflare D1 Database Migrations

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Worker backed by Cloudflare D1 has accumulated 30 migration SQL files. Developers run
`wrangler d1 migrations apply` locally before deploying, but the migrations are sometimes
applied in the wrong order, skipped after a git rebase, or run against the wrong environment.
Production has been out of sync with staging twice this month. The team needs an automated,
ordered, environment-gated migration pipeline integrated into GitHub Actions.

## Context

Cloudflare D1 migrations work differently from traditional server-side database migrations:

- Migrations are SQL files in a directory (by convention `migrations/`) numbered with a prefix
  (e.g., `0001_create_users.sql`, `0002_add_email_index.sql`)
- `wrangler d1 migrations apply {DATABASE_NAME}` applies all pending migrations in numeric order
- Wrangler maintains a `d1_migrations` table inside each D1 database to track which migrations
  have been applied
- D1 has no transactional rollback for DDL — a failed migration may partially apply, leaving
  the schema in an inconsistent state
- `--remote` applies to the real Cloudflare edge database; without it, Wrangler applies to a
  local SQLite file used by Miniflare

The pipeline must:
1. Validate SQL syntax before any apply (lint step)
2. Apply migrations to a **preview** D1 database on every PR #<number>. Apply migrations to **staging** D1 on merge to `main` before deploying the Worker
4. Apply migrations to **production** D1 only after staging deploy succeeds and a human approves
5. Detect and alert on migration drift (staging schema != production schema)

## Section 1: Migration Validation and Lint on Every PR

```yaml
# .github/workflows/d1-migrations-pr.yml
name: D1 Migration Lint

on:
  pull_request:
    paths:
      - 'migrations/**'
      - 'wrangler.toml'
      - 'wrangler.*.toml'

jobs:
  validate-migrations:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      # Check migration file naming convention
      - name: Validate migration filenames
        run: |
          ERRORS=0
          for f in migrations/*.sql; do
            [[ -f "$f" ]] || continue
            BASENAME=$(basename "$f")
            if ! [[ "$BASENAME" =~ ^[0-9]{4}_[a-z0-9_]+\.sql$ ]]; then
              echo "::error file=${f}::Migration filename must match pattern: 0001_description.sql"
              ERRORS=$((ERRORS+1))
            fi
          done
          [[ "$ERRORS" -eq 0 ]] || exit 1

      # Check no gaps in migration sequence
      - name: Check sequence continuity
        run: |
          PREV=0
          for f in $(ls migrations/*.sql 2>/dev/null | sort); do
            BASENAME=$(basename "$f")
            NUM="${BASENAME%%_*}"
            NUM_INT=$((10#$NUM))
            EXPECTED=$((PREV+1))
            if [[ "$NUM_INT" -ne "$EXPECTED" ]]; then
              echo "::error file=migrations/::Gap detected: expected migration $(printf '%04d' $EXPECTED), found ${NUM}"
              exit 1
            fi
            PREV=$NUM_INT
          done
          echo "Migration sequence is continuous (1 through $PREV)"

      # Validate SQL syntax using sqlite3 (local dry-run)
      - name: Install sqlite3
        run: sudo apt-get install -y sqlite3

      - name: Syntax-check each new migration
        run: |
          # Only check migrations added in this PR
          CHANGED=$(git diff --name-only origin/${{ github.base_ref }}...HEAD -- migrations/)
          if [[ -z "$CHANGED" ]]; then
            echo "No migration files changed."
            exit 0
          fi
          TMPDB=$(mktemp --suffix=.db)
          # Apply all existing migrations to a temp DB first
          for f in $(ls migrations/*.sql | sort); do
            BASENAME=$(basename "$f")
            if ! echo "$CHANGED" | grep -q "$BASENAME"; then
              sqlite3 "$TMPDB" < "$f" 2>&1 || true  # Ignore pre-existing migration errors
            fi
          done
          # Now apply only the new migrations and check for SQL errors
          FAILED=0
          for f in $CHANGED; do
            echo "Validating $f..."
            if ! sqlite3 "$TMPDB" < "$f" 2>&1; then
              echo "::error file=${f}::SQL syntax error in migration"
              FAILED=$((FAILED+1))
            fi
          done
          rm -f "$TMPDB"
          [[ "$FAILED" -eq 0 ]] || exit 1

      # Check for dangerous migration patterns (no rollback possible in D1)
      - name: Check for destructive operations
        run: |
          CHANGED=$(git diff --name-only origin/${{ github.base_ref }}...HEAD -- migrations/)
          [[ -z "$CHANGED" ]] && exit 0
          WARN=0
          for f in $CHANGED; do
            if grep -Eiq '^\s*(DROP TABLE|DROP COLUMN|ALTER TABLE.*DROP)' "$f"; then
              echo "::warning file=${f}::Destructive operation detected. Verify you have a data backup and a rollback plan. D1 DDL cannot be rolled back."
              WARN=$((WARN+1))
            fi
          done
          # Warn but do not fail — the human reviewer decides.

      - name: Write step summary
        run: |
          TOTAL=$(ls migrations/*.sql 2>/dev/null | wc -l)
          CHANGED=$(git diff --name-only origin/${{ github.base_ref }}...HEAD -- migrations/ | wc -l)
          echo "## D1 Migration Validation" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          echo "| Metric | Value |" >> "$GITHUB_STEP_SUMMARY"
          echo "|---|---|" >> "$GITHUB_STEP_SUMMARY"
          echo "| Total migrations | ${TOTAL} |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Changed in this PR | ${CHANGED} |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Syntax check | Passed |" >> "$GITHUB_STEP_SUMMARY"
```

## Section 2: Apply Migrations to Staging on Merge to Main

```yaml
# .github/workflows/d1-migrations-staging.yml
name: D1 Staging Migration + Deploy

on:
  push:
    branches: [main]

# Prevent concurrent migration runs — D1 does not handle concurrent DDL safely
concurrency:
  group: d1-migrations-staging
  cancel-in-progress: false  # Never cancel a running migration

jobs:
  migrate-staging:
    runs-on: ubuntu-latest
    environment: staging          # Links to the GitHub Environment with staging secrets
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      # Show pending migrations before applying
      - name: Show pending migrations (staging)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          echo "## Pending D1 Migrations (staging)" >> "$GITHUB_STEP_SUMMARY"
          pnpm wrangler d1 migrations list STAGING_DB --remote --env staging \
            --json 2>/dev/null | \
            node -e "
              const data = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8'));
              const pending = data.filter(m => !m.applied_at);
              if (pending.length === 0) {
                console.log('No pending migrations.');
                process.stdout.write('No pending migrations.\n');
              } else {
                pending.forEach(m => console.log('- ' + m.name));
              }
            " | tee -a "$GITHUB_STEP_SUMMARY"

      - name: Apply migrations to staging D1
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          pnpm wrangler d1 migrations apply STAGING_DB --remote --env staging

      - name: Verify migration table state
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          pnpm wrangler d1 execute STAGING_DB \
            --command "SELECT name, applied_at FROM d1_migrations ORDER BY id DESC LIMIT 5;" \
            --remote --env staging

  deploy-staging-worker:
    needs: migrate-staging
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Deploy Worker to staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: pnpm wrangler deploy --env staging
```

## Section 3: Gated Production Migration with Drift Detection

```yaml
# .github/workflows/d1-migrations-production.yml
name: D1 Production Migration + Deploy

on:
  workflow_dispatch:
    inputs:
      confirm:
        description: 'Type "production" to confirm production migration'
        required: true
        type: string

jobs:
  gate-check:
    runs-on: ubuntu-latest
    steps:
      - name: Validate confirmation
        run: |
          if [[ "${{ inputs.confirm }}" != "production" ]]; then
            echo "::error::Confirmation text must be exactly 'production'. Got: ${{ inputs.confirm }}"
            exit 1
          fi

  drift-detection:
    needs: gate-check
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile

      # Compare applied migrations in staging vs production
      # If staging has migrations that production doesn't, that's expected (they're about to be applied).
      # If production has migrations that staging doesn't, that's drift — fail hard.
      - name: Detect migration drift
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          STAGING_APPLIED=$(pnpm wrangler d1 execute STAGING_DB \
            --command "SELECT name FROM d1_migrations WHERE applied_at IS NOT NULL ORDER BY id;" \
            --remote --env staging --json 2>/dev/null | \
            node -e "const d=JSON.parse(require('fs').readFileSync('/dev/stdin','utf8')); \
              console.log(d[0]?.results?.map(r=>r.name).join('\n') ?? '')")

          PROD_APPLIED=$(pnpm wrangler d1 execute PROD_DB \
            --command "SELECT name FROM d1_migrations WHERE applied_at IS NOT NULL ORDER BY id;" \
            --remote --env production --json 2>/dev/null | \
            node -e "const d=JSON.parse(require('fs').readFileSync('/dev/stdin','utf8')); \
              console.log(d[0]?.results?.map(r=>r.name).join('\n') ?? '')")

          # Find migrations in prod but NOT in staging (dangerous drift)
          DRIFT=$(comm -23 \
            <(echo "$PROD_APPLIED" | sort) \
            <(echo "$STAGING_APPLIED" | sort))

          if [[ -n "$DRIFT" ]]; then
            echo "::error::Production has migrations not in staging — schema drift detected:"
            echo "$DRIFT"
            exit 1
          fi

          echo "No drift detected. Staging is a superset of production."

  migrate-production:
    needs: [drift-detection]
    runs-on: ubuntu-latest
    environment: production   # This environment requires a human approval in GitHub
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile

      - name: Show pending migrations (production)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          pnpm wrangler d1 migrations list PROD_DB --remote --env production

      - name: Apply migrations to production D1
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          pnpm wrangler d1 migrations apply PROD_DB --remote --env production

  deploy-production-worker:
    needs: migrate-production
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile

      - name: Deploy Worker to production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: pnpm wrangler deploy --env production
```

## Anti-patterns

- **Running `wrangler d1 migrations apply` in the same job as `wrangler deploy` without a
  dependency order** — if the Worker is deployed before migrations complete, requests may hit
  code expecting new columns that don't exist yet. Always gate `deploy` on migration success.
- **Not setting `concurrency: cancel-in-progress: false`** — if two PRs merge in quick
  succession, a cancelled migration job may leave the `d1_migrations` table in an inconsistent
  state, preventing subsequent migrations from running.
- **Using `--local` flag in production-like pipelines** — `--local` applies migrations to a
  local SQLite file, not to the remote D1 database. Always use `--remote` in CI.
- **Storing migration files in a non-sequential numbering scheme** — migrations must be applied
  in numeric order. If a developer creates `0003_` before `0002_` is merged, rebase conflicts
  cause sequence gaps and Wrangler refuses to apply.
- **No backup before destructive migrations** — D1 does not support DDL transactions. A
  `DROP COLUMN` that fails halfway cannot be rolled back. Always export the D1 database to R2
  before any migration containing `DROP` or `ALTER TABLE ... DROP`.

## Gotchas

- **`d1_migrations` table must exist before `migrations list` or `migrations apply`** — Wrangler
  creates this table on the first `apply` call. If you try to query it before any migration
  has ever been applied, the query returns an error. The `--json` flag helps with parsing but
  does not suppress this error.
- **D1 API token needs `D1:Edit` permission** — the Cloudflare API token used in CI must have
  the `D1:Edit` permission on the specific database. A general `Edit` token works but violates
  least privilege. Create a token scoped to the specific D1 database ID.
- **Migration file encoding** — D1 requires UTF-8 SQL files without BOM. SQL files created on
  Windows with certain editors include a BOM that causes Wrangler to fail with a parser error.
  Add a pre-commit hook: `file migrations/*.sql | grep -q BOM && exit 1`.
- **`wrangler.toml` database binding name must match the `DATABASE_NAME` argument** — the
  positional argument to `wrangler d1 migrations apply` is the database name declared in
  `wrangler.toml` under `[[d1_databases]]`, not the Cloudflare dashboard name. These can differ.
- **Preview environments share the same D1 binding name** — if your PR preview Workers use the
  same D1 binding name but a different `database_id` (pointing at a preview database), ensure
  your migration workflow targets the preview `database_id`, not production.

## Verification

```bash
# List all applied migrations in staging
wrangler d1 execute STAGING_DB \
  --command "SELECT id, name, applied_at FROM d1_migrations ORDER BY id;" \
  --remote --env staging

# Count pending migrations
wrangler d1 migrations list STAGING_DB --remote --env staging \
  | grep -c "No"

# Dry-run a migration (inspect SQL without applying)
cat migrations/0005_add_sessions_table.sql | \
  wrangler d1 execute STAGING_DB --command - --remote --env staging --dry-run

# Compare schemas between staging and production (column-level diff)
wrangler d1 execute STAGING_DB \
  --command "SELECT tbl_name, sql FROM sqlite_master WHERE type='table' ORDER BY tbl_name;" \
  --remote --env staging --json > /tmp/staging_schema.json

wrangler d1 execute PROD_DB \
  --command "SELECT tbl_name, sql FROM sqlite_master WHERE type='table' ORDER BY tbl_name;" \
  --remote --env production --json > /tmp/prod_schema.json

diff /tmp/staging_schema.json /tmp/prod_schema.json
```

## Related

- `github-actions-cloudflare-deploy-workflow.md` — base deploy workflow this pipeline extends
- `github-actions-environments.md` — setting up staging and production environments with approval gates
- `github-actions-deployment-gates.md` — custom deployment protection rules for D1 environments
- `github-actions-oidc-cloudflare.md` — OIDC-based auth to replace API token secrets
- `github-actions-concurrency.md` — concurrency group patterns to prevent parallel migration runs
- `github-actions-cache-invalidation-workers-builds.md` — caching the Worker build that deploys after migration

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#concurrency
- https://developers.cloudflare.com/api/resources/d1/
