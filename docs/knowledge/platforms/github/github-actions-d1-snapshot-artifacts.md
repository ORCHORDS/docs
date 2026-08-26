# GitHub Actions D1 Database Snapshot Artifacts

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A CI/CD pipeline that runs Cloudflare D1 schema migrations has no rollback artefact: when a
migration fails halfway through production, there is no point-in-time copy of the database
to restore from. Capturing a D1 snapshot before each migration run and uploading it as a
GitHub Actions artifact gives a downloadable SQLite file that can be re-applied to a new D1
database to recover state. Secondary use-case: snapshot diffing to detect unexpected schema
drift between environments.

## Context

Cloudflare D1 is built on SQLite and supports an export API (`wrangler d1 export`) that
produces a standard `.sql` dump. GitHub Actions artifacts can hold up to 500 MB per file
(2 GB with `actions/upload-artifact@v4` chunked uploads) and are retained for a configurable
number of days. The snapshot workflow runs before the migration job using a `needs` dependency
so the archive is always available even when the migration step fails. The snapshot is also
useful as an integration-test fixture that CI jobs can import into a local miniflare D1
instance without hitting the production API.

## Pre-Migration Snapshot Job

The snapshot job exports the production database to a `.sql` file and uploads it as an
artifact named with the commit SHA for traceability.

```yaml
# .github/workflows/migrate.yml
name: D1 Migrate

on:
  push:
    branches: [main]
    paths:
      - 'migrations/**'
      - 'wrangler.toml'

jobs:
  snapshot:
    name: Snapshot D1 before migration
    runs-on: ubuntu-24.04
    permissions:
      contents: read

    outputs:
      snapshot-artifact-name: ${{ steps.set-name.outputs.name }}

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Set snapshot artifact name
        id: set-name
        run: echo "name=d1-snapshot-${{ github.sha }}" >> "$GITHUB_OUTPUT"

      - name: Export D1 snapshot
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          mkdir -p snapshots
          pnpm wrangler d1 export "${{ vars.D1_DATABASE_NAME }}" \
            --remote \
            --output snapshots/pre-migration.sql

      - name: Compress snapshot
        run: gzip -9 snapshots/pre-migration.sql

      - name: Upload snapshot artifact
        uses: actions/upload-artifact@v4
        with:
          name: ${{ steps.set-name.outputs.name }}
          path: snapshots/pre-migration.sql.gz
          retention-days: 30
          if-no-files-found: error

  migrate:
    name: Run D1 migrations
    runs-on: ubuntu-24.04
    needs: snapshot
    permissions:
      contents: read

    environment:
      name: production

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Apply migrations
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          pnpm wrangler d1 migrations apply "${{ vars.D1_DATABASE_NAME }}" --remote
```

## Using the Snapshot as a Test Fixture

The snapshot can be restored into a local miniflare D1 instance during integration tests,
giving CI a realistic data set without touching the production database.

```typescript
// tests/setup/d1-fixture.ts
import { execSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { gunzipSync } from "node:zlib";

const FIXTURE_PATH = process.env.D1_FIXTURE_PATH ?? "snapshots/pre-migration.sql.gz";

export async function loadD1Fixture(
  db: D1Database,
  fixturePath = FIXTURE_PATH
): Promise<void> {
  if (!existsSync(fixturePath)) {
    console.warn(`D1 fixture not found at ${fixturePath}, skipping seed`);
    return;
  }

  const compressed = readFileSync(fixturePath);
  const sql = gunzipSync(compressed).toString("utf-8");

  // Split on statement boundaries and batch-execute
  const statements = sql
    .split(/;\s*\n/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && !s.startsWith("--"));

  await db.batch(statements.map((sql) => db.prepare(sql)));
}
```

## Schema Drift Detection Job

Compare snapshots across environments by extracting only `CREATE TABLE` statements and
diffing them. A mismatch between staging and production schemas fails the workflow before
any migration runs.

```yaml
  drift-check:
    name: Detect schema drift
    runs-on: ubuntu-24.04
    needs: []
    permissions:
      contents: read
    if: github.event_name == 'pull_request'

    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile

      - name: Export staging schema
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          pnpm wrangler d1 export "${{ vars.D1_STAGING_DATABASE_NAME }}" \
            --remote --no-data --output staging-schema.sql

      - name: Export production schema
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          pnpm wrangler d1 export "${{ vars.D1_DATABASE_NAME }}" \
            --remote --no-data --output prod-schema.sql

      - name: Compare schemas
        run: |
          if ! diff <(grep "^CREATE" staging-schema.sql | sort) \
                    <(grep "^CREATE" prod-schema.sql | sort); then
            echo "Schema drift detected between staging and production."
            exit 1
          fi
          echo "Schemas match."
```

## Anti-patterns

- Uploading uncompressed `.sql` files for large databases — a 50 MB dump compresses to ~5 MB
  with gzip; skipping compression burns artifact storage quota and slows upload/download.
- Setting `retention-days: 1` on snapshot artifacts — when a production incident occurs two
  days after a bad migration, the snapshot needed for recovery is already gone.
- Running the snapshot job after the migration job — if the migration corrupts the schema,
  the snapshot captures the corrupted state, not the recoverable pre-migration state.

## Gotchas

- `wrangler d1 export --remote` counts against D1 read-unit quota; for large databases
  (> 1 GB) run exports only on merge to main, not on every pull request commit.
- The exported SQL uses SQLite dialect and cannot be directly imported into a Postgres or
  MySQL-backed staging environment; use the snapshot only for D1-to-D1 recovery.
- GitHub artifact names must be unique per workflow run; use `github.sha` or `github.run_id`
  in the artifact name to prevent collisions when the workflow is re-triggered on the same
  commit.

## Verification

```bash
# Download and inspect the latest snapshot artifact via GitHub CLI
gh run download --name "d1-snapshot-$(git rev-parse HEAD)" --dir ./restored

# Decompress and verify it is valid SQL
gunzip -c restored/pre-migration.sql.gz | head -40

# Restore into a local SQLite file for inspection
gunzip -c restored/pre-migration.sql.gz | sqlite3 /tmp/d1-restore.db
sqlite3 /tmp/d1-restore.db ".tables"
sqlite3 /tmp/d1-restore.db ".schema"
```

## Related

- `github/github-actions-cloudflare-d1-migration-pipeline.md`
- `github/github-actions-artifact-upload.md`
- `github/github-actions-artifact-log-retention-evidence-policy.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
