# D1 Backup Before Migration in CI: Export to R2, Verify, Migrate, Restore on Failure

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Running `wrangler d1 migrations apply` in CI against a production D1 database with no prior backup. If the migration contains a destructive statement (DROP COLUMN, DELETE, irreversible schema change) and something goes wrong mid-migration, there is no snapshot to restore from. The fix is to export the database to R2 before every migration run, verify the export is non-empty, proceed with migration, and have a tested restore path ready.

## Context

D1 supports `wrangler d1 export` which produces a SQLite-compatible SQL dump. R2 is the ideal durable store for these dumps because it lives within the same Cloudflare account and can be accessed without extra credentials in Workers. The CI pipeline exports, stores in R2 with a timestamped key, then runs migrations. On failure, a restore script re-imports the dump.

---

## Section 1: Pre-Migration Export Script

```bash
#!/usr/bin/env bash
# scripts/d1-backup.sh
# Exports D1 to a local SQL file and uploads to R2.
# Usage: ./scripts/d1-backup.sh <database-name> <r2-bucket-name> [output-dir]

set -euo pipefail

DB_NAME="${1:?DB_NAME required}"
R2_BUCKET="${2:?R2_BUCKET required}"
OUT_DIR="${3:-/tmp/d1-backups}"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
OUT_FILE="${OUT_DIR}/${DB_NAME}-${TIMESTAMP}.sql"
R2_KEY="backups/${DB_NAME}/${TIMESTAMP}.sql"

mkdir -p "$OUT_DIR"

echo "[d1-backup] Exporting ${DB_NAME} → ${OUT_FILE}"
npx wrangler d1 export "$DB_NAME" --remote --output "$OUT_FILE"

# Verify the export is non-trivially sized (>1 KB)
FILE_SIZE=$(wc -c < "$OUT_FILE")
if [ "$FILE_SIZE" -lt 1024 ]; then
  echo "::error::[d1-backup] Export suspiciously small: ${FILE_SIZE} bytes. Aborting."
  exit 1
fi
echo "[d1-backup] Export size: ${FILE_SIZE} bytes — OK"

# Upload to R2 using wrangler r2 object put
echo "[d1-backup] Uploading to R2: s3://${R2_BUCKET}/${R2_KEY}"
npx wrangler r2 object put "${R2_BUCKET}/${R2_KEY}" \
  --file "$OUT_FILE" \
  --content-type "text/plain"

echo "[d1-backup] Backup complete: ${R2_KEY}"
# Emit the key so CI can pass it to the restore step if needed
echo "R2_BACKUP_KEY=${R2_KEY}" >> "${GITHUB_ENV:-/dev/null}"
echo "R2_BACKUP_KEY=${R2_KEY}"
```

## Section 2: GitHub Actions Workflow

```yaml
# .github/workflows/d1-migrate.yml
name: D1 Migration

on:
  workflow_dispatch:
    inputs:
      environment:
        description: Target environment
        required: true
        default: production
        type: choice
        options: [production, staging]
  push:
    branches: [main]
    paths:
      - 'migrations/**'

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  DB_NAME: my-production-db
  R2_BUCKET: my-d1-backups

jobs:
  migrate:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment || 'production' }}
    concurrency:
      group: d1-migrate-${{ inputs.environment || 'production' }}
      cancel-in-progress: false   # never cancel a migration in flight

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Export D1 backup to R2
        id: backup
        run: |
          chmod +x scripts/d1-backup.sh
          ./scripts/d1-backup.sh "$DB_NAME" "$R2_BUCKET"
          echo "backup_key=${R2_BACKUP_KEY}" >> "$GITHUB_OUTPUT"

      - name: List pending migrations
        run: |
          npx wrangler d1 migrations list "$DB_NAME" --remote

      - name: Apply migrations
        id: migrate
        run: |
          npx wrangler d1 migrations apply "$DB_NAME" \
            --remote \
            --batch-size 5
        continue-on-error: true

      - name: Restore from backup on failure
        if: steps.migrate.outcome == 'failure'
        env:
          R2_BACKUP_KEY: ${{ steps.backup.outputs.backup_key }}
        run: |
          echo "::error::Migration failed. Restoring backup: ${R2_BACKUP_KEY}"
          chmod +x scripts/d1-restore.sh
          ./scripts/d1-restore.sh "$DB_NAME" "$R2_BUCKET" "$R2_BACKUP_KEY"

      - name: Fail job after restore
        if: steps.migrate.outcome == 'failure'
        run: exit 1

      - name: Verify schema after migration
        run: |
          npx wrangler d1 execute "$DB_NAME" --remote \
            --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
```

## Section 3: Restore Script

```bash
#!/usr/bin/env bash
# scripts/d1-restore.sh
# Downloads backup from R2 and imports into D1.
# Usage: ./scripts/d1-restore.sh <database-name> <r2-bucket> <r2-key>

set -euo pipefail

DB_NAME="${1:?DB_NAME required}"
R2_BUCKET="${2:?R2_BUCKET required}"
R2_KEY="${3:?R2_KEY required}"
LOCAL_FILE="/tmp/d1-restore-${DB_NAME}.sql"

echo "[d1-restore] Downloading s3://${R2_BUCKET}/${R2_KEY} → ${LOCAL_FILE}"
npx wrangler r2 object get "${R2_BUCKET}/${R2_KEY}" \
  --file "$LOCAL_FILE"

FILE_SIZE=$(wc -c < "$LOCAL_FILE")
echo "[d1-restore] Downloaded ${FILE_SIZE} bytes"

if [ "$FILE_SIZE" -lt 1024 ]; then
  echo "::error::[d1-restore] Downloaded file suspiciously small. Aborting restore."
  exit 1
fi

echo "[d1-restore] Importing into D1 database: ${DB_NAME}"
npx wrangler d1 execute "$DB_NAME" \
  --remote \
  --file "$LOCAL_FILE"

echo "[d1-restore] Restore complete"
```

## Section 4: Backup Retention Worker (TypeScript)

```typescript
// workers/backup-janitor/src/index.ts
// Cron Worker: deletes R2 backup objects older than 30 days.

import { Env } from './types';

const RETENTION_DAYS = 30;

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - RETENTION_DAYS);

    let cursor: string | undefined;
    let deleted = 0;

    do {
      const list = await env.BACKUP_BUCKET.list({
        prefix: 'backups/',
        cursor,
        limit: 100,
      });

      const toDelete = list.objects.filter(obj => obj.uploaded < cutoff);

      await Promise.all(
        toDelete.map(obj => env.BACKUP_BUCKET.delete(obj.key))
      );

      deleted += toDelete.length;
      cursor = list.truncated ? list.cursor : undefined;
    } while (cursor);

    console.log(`[backup-janitor] Deleted ${deleted} old backup(s) older than ${RETENTION_DAYS} days`);
  },
};
```

```toml
# workers/backup-janitor/wrangler.toml
name = "backup-janitor"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "BACKUP_BUCKET"
bucket_name = "my-d1-backups"

[triggers]
crons = ["0 3 * * *"]  # daily at 03:00 UTC
```

## Anti-patterns

- **Skipping the size check**: An empty or near-empty export (e.g., `PRAGMA foreign_keys=ON;` only) will pass `wrangler d1 export` with exit code 0. Always verify file size.
- **Using `--local` flag on export**: `--local` exports from the local dev database, not the remote production D1. Always use `--remote` in CI.
- **No concurrency lock**: Two migration jobs running simultaneously can interleave SQL statements and corrupt the schema. Use `concurrency.group` in the workflow.
- **Restoring with `--local`**: The restore must target `--remote`, same as the migration.

## Gotchas

- `wrangler d1 export` requires the `D1: Write` token permission — the same token used for migrations. A read-only token is insufficient.
- Large D1 databases (>500 MB) may hit Wrangler's export timeout. For very large databases, consider exporting only the schema (`--no-data`) plus incremental row dumps per table.
- `wrangler r2 object put` does not create the bucket if it doesn't exist. Create the bucket via `wrangler r2 bucket create` or the Cloudflare dashboard before the first workflow run.
- D1 is SQLite-based. The SQL dump from `d1 export` uses SQLite dialect. Standard MySQL/Postgres restore tools will not work.

## Verification

```bash
# Manual backup test (staging database)
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
./scripts/d1-backup.sh my-staging-db my-d1-backups

# Confirm in R2
npx wrangler r2 object list my-d1-backups --prefix backups/

# Test restore into a throwaway local DB
sqlite3 /tmp/test-restore.db < /tmp/d1-backups/my-staging-db-*.sql
sqlite3 /tmp/test-restore.db '.tables'
```

## Related

- `documentation/docs/policies/github/github-actions-workers-post-deploy-health-check.md`
- `documentation/d1/d1-schema-migrations-best-practices.md`
- `documentation/r2/r2-bucket-lifecycle-policies.md`

## Sources

- https://developers.cloudflare.com/d1/wrangler-commands/#d1-export
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs
