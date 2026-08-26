# D1 Time Travel: Point-in-Time Restore

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A destructive migration ran against your D1 database and you need to restore data to a known-good state before the migration ran. Cloudflare D1 Time Travel lets you restore a database to any point within the last 30 days using a timestamp or a bookmark token, without provisioning a separate replica.

## Context

- Runtime: Cloudflare Workers (ESM)
- Database: Cloudflare D1 (SQLite-compatible)
- Tooling: Wrangler CLI v3.x
- Use-case: disaster recovery, bad migration rollback, data archaeology

---

## Section 1: Retrieve a Bookmark Before Running Migrations

Capture a bookmark immediately before every destructive migration so you have a deterministic restore target.

```bash
# Capture a bookmark BEFORE the migration
wrangler d1 time-travel info YOUR_DB_NAME \
  --timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --remote
# Output example:
# {
#   "bookmark": "0000000000000001-0000000000000001",
#   "timestamp": "2026-08-24T10:00:00Z"
# }

# Save the bookmark to a file for later reference
wrangler d1 time-travel info YOUR_DB_NAME \
  --timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --remote \
  | jq -r '.bookmark' > .pre-migration-bookmark

echo "Saved bookmark: $(cat .pre-migration-bookmark)"
```

---

## Section 2: Restore to a Timestamp

Restore to a specific wall-clock time using an ISO-8601 timestamp.

```bash
# Restore to a specific UTC timestamp
wrangler d1 time-travel restore YOUR_DB_NAME \
  --timestamp "2026-08-24T09:55:00Z" \
  --remote

# The CLI will prompt for confirmation:
# Are you sure you want to restore YOUR_DB_NAME to 2026-08-24T09:55:00Z? (y/N)
# Type y to proceed.

# For scripted / non-interactive use, pipe the confirmation:
echo "y" | wrangler d1 time-travel restore YOUR_DB_NAME \
  --timestamp "2026-08-24T09:55:00Z" \
  --remote
```

---

## Section 3: Restore Using a Saved Bookmark

Bookmarks are more reliable than timestamps because they are exact sequence positions rather than wall-clock approximations.

```bash
#!/usr/bin/env bash
# scripts/restore-from-bookmark.sh

set -euo pipefail

DB_NAME="${1:?Usage: $0 <db-name> [bookmark]}"
BOOKMARK="${2:-$(cat .pre-migration-bookmark 2>/dev/null || echo "")}"

if [[ -z "$BOOKMARK" ]]; then
  echo "ERROR: No bookmark provided and .pre-migration-bookmark not found."
  exit 1
fi

echo "Restoring $DB_NAME to bookmark $BOOKMARK ..."
echo "y" | wrangler d1 time-travel restore "$DB_NAME" \
  --bookmark "$BOOKMARK" \
  --remote

echo "Restore complete."
```

```bash
# Run the restore script
bash scripts/restore-from-bookmark.sh prod-db
```

---

## Section 4: Scripting Full Recovery Workflow

A complete shell script that bookmarks, runs a migration, detects failure, and auto-reverts.

```bash
#!/usr/bin/env bash
# scripts/safe-migrate.sh

set -euo pipefail

DB_NAME="${1:?Usage: $0 <db-name> <migration-sql>}"
MIGRATION_FILE="${2:?}"
BOOKMARK_FILE=".rollback-bookmark"

# 1. Capture pre-migration bookmark
echo "Capturing pre-migration bookmark..."
wrangler d1 time-travel info "$DB_NAME" \
  --timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --remote \
  | jq -r '.bookmark' > "$BOOKMARK_FILE"

PRE_BOOKMARK=$(cat "$BOOKMARK_FILE")
echo "Bookmark: $PRE_BOOKMARK"

# 2. Run migration
echo "Running migration: $MIGRATION_FILE"
if ! wrangler d1 execute "$DB_NAME" --file "$MIGRATION_FILE" --remote; then
  echo "Migration FAILED. Restoring from bookmark $PRE_BOOKMARK ..."
  echo "y" | wrangler d1 time-travel restore "$DB_NAME" \
    --bookmark "$PRE_BOOKMARK" \
    --remote
  echo "Auto-restore complete."
  exit 1
fi

echo "Migration succeeded."
```

---

## Section 5: Validation Queries Post-Restore

After restore, verify the database is in the expected state before routing live traffic back.

```typescript
// src/db/verify-restore.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface VerificationResult {
  table: string;
  rowCount: number;
  latestTimestamp: string | null;
  ok: boolean;
}

export async function verifyRestore(
  db: D1Database,
  expectedCounts: Record<string, number>,
): Promise<VerificationResult[]> {
  const results: VerificationResult[] = [];

  for (const [table, expectedMin] of Object.entries(expectedCounts)) {
    const row = await db
      .prepare(
        `SELECT COUNT(*) as cnt,
                MAX(created_at) as latest
         FROM ${table}`,
      )
      .first<{ cnt: number; latest: string | null }>();

    const rowCount = row?.cnt ?? 0;
    const ok = rowCount >= expectedMin;

    results.push({
      table,
      rowCount,
      latestTimestamp: row?.latest ?? null,
      ok,
    });

    if (!ok) {
      console.error(
        `VERIFY FAIL: ${table} has ${rowCount} rows, expected >= ${expectedMin}`,
      );
    } else {
      console.log(`VERIFY OK: ${table} has ${rowCount} rows`);
    }
  }

  return results;
}
```

```bash
# Run validation via a one-off Worker script after restore
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT name, COUNT(*) FROM sqlite_master GROUP BY name;" \
  --remote
```

---

## Anti-patterns

- Restoring directly to production without testing the restored state against a staging copy first.
- Using wall-clock timestamps without accounting for propagation lag — bookmarks are always safer.
- Skipping pre-migration bookmark capture and relying on guessing the right timestamp later.
- Restoring while active Workers are still writing to the database (causes bookmark drift).
- Assuming Time Travel covers schema-only changes that deleted virtual tables — verify manually.

## Gotchas

- Time Travel retention is 30 days; anything older requires manual backup snapshots.
- `--timestamp` is resolved to the nearest available commit position, which may be a few seconds earlier than requested.
- Bookmarks are database-scoped and not transferable across databases or accounts.
- During the restore operation the database is briefly unavailable; Workers will receive `D1_ERROR` responses.
- `wrangler d1 time-travel restore` does not support `--json` output yet; parse stdout carefully in scripts.

## Verification

```bash
# Check current database state and generation after restore
wrangler d1 info YOUR_DB_NAME --remote

# Quick row-count sanity check on critical tables
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT 'users' as t, COUNT(*) as n FROM users \
             UNION ALL \
             SELECT 'orders', COUNT(*) FROM orders;" \
  --remote

# Confirm the bad migration table no longer exists (if it was a CREATE TABLE migration)
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" \
  --remote
```

## Related

- `documentation/docs/policies/database/d1-connection-retry-exponential-backoff.md`
- `documentation/docs/policies/database/d1-trigger-audit-log-application-layer.md`

## Sources

- https://developers.cloudflare.com/d1/reference/time-travel/
- https://developers.cloudflare.com/d1/wrangler-commands/#d1-time-travel-info
- https://developers.cloudflare.com/d1/wrangler-commands/#d1-time-travel-restore
