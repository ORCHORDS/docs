# Cloudflare D1 Time Travel Point-in-Time Recovery

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A bad migration or a Worker bug corrupts rows in a D1 production database.
Because D1 is a serverless SQLite service without a manual backup UI, operators
need a repeatable runbook for restoring to a prior state.  Cloudflare's D1 Time
Travel feature retains up to 30 days of write-ahead log history and allows
non-destructive restoration to any second within that window, but the API
surface and recovery procedure are not obvious from the documentation.

## Context

D1 Time Travel is enabled by default on all D1 databases.  It works by
replaying WAL entries from a write-ahead log that Cloudflare retains
automatically — no user action is required to activate it.  Restoration creates
a bookmark (a point-in-time snapshot label) and then restores the database to
that bookmark in-place.  The operation is atomic but does take the database
offline briefly (typically < 30 seconds for databases under 1 GB).

Time Travel is available via:
- `wrangler d1 time-travel` CLI subcommands
- Cloudflare REST API (`/client/v4/accounts/{id}/d1/database/{db_id}/time_travel/bookmarks`)
- No Terraform resource yet exists (as of mid-2026); use `local-exec` or CI scripts.

---

## 1. Listing Available Timestamps

```bash
# Show the earliest and latest timestamps available for recovery
wrangler d1 time-travel info example project-production-db

# Output example:
# min_timestamp: 2026-07-24T10:42:00Z
# max_timestamp: 2026-08-23T14:00:00Z
# database_size: 128 MB
```

---

## 2. Creating a Named Bookmark Before a Risky Migration

```bash
# Always create a bookmark before running a destructive migration
BOOKMARK=$(wrangler d1 time-travel bookmark create example project-production-db \
  --description "pre-migration-2026-08-23" \
  --format json | jq -r '.result.bookmark_id')

echo "Bookmark created: $BOOKMARK"
# Store this in your incident runbook or CI artifact

# Run the migration
wrangler d1 migrations apply example project-production-db --remote
```

Integrate into CI:

```yaml
# .github/workflows/d1-migrate.yml
- name: Create pre-migration bookmark
  id: bookmark
  run: |
    BKID=$(wrangler d1 time-travel bookmark create example project-production-db \
      --description "pre-migration-${{ github.run_id }}" \
      --format json | jq -r '.result.bookmark_id')
    echo "bookmark_id=$BKID" >> "$GITHUB_OUTPUT"

- name: Apply migrations
  run: wrangler d1 migrations apply example project-production-db --remote

- name: Output rollback command
  run: |
    echo "To rollback, run:"
    echo "wrangler d1 time-travel restore example project-production-db \
      --bookmark ${{ steps.bookmark.outputs.bookmark_id }}"
```

---

## 3. Restoring to a Named Bookmark

```bash
# Dry-run first — verifies the bookmark is valid without applying changes
wrangler d1 time-travel restore example project-production-db \
  --bookmark "$BOOKMARK" \
  --dry-run

# Apply the restore (this takes the DB offline briefly)
wrangler d1 time-travel restore example project-production-db \
  --bookmark "$BOOKMARK"

# Confirm restoration completed
wrangler d1 execute example project-production-db \
  --remote \
  --command "SELECT count(*) FROM sqlite_master;"
```

---

## 4. Restoring to an Arbitrary Timestamp (No Pre-created Bookmark)

```bash
# Restore to one hour before the incident was detected
TARGET_TS="2026-08-23T12:30:00Z"

wrangler d1 time-travel restore example project-production-db \
  --timestamp "$TARGET_TS"

# Via REST API (useful from Workers or automation scripts)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/time_travel/restore" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"timestamp\": \"${TARGET_TS}\"}" | jq '.result'
```

---

## 5. Terraform Local-exec Bookmark Automation

Because no native Terraform resource exists, use `local-exec` to hook bookmark
creation into the plan/apply lifecycle:

```hcl
# infra/d1_backup_hook.tf

resource "null_resource" "d1_pre_migration_bookmark" {
  triggers = {
    migration_hash = filemd5("${path.module}/../migrations/latest.sql")
  }

  provisioner "local-exec" {
    command = <<-EOT
      wrangler d1 time-travel bookmark create ${var.d1_database_name} \
        --description "terraform-apply-$(date -u +%Y%m%dT%H%M%SZ)" \
        --format json > /tmp/d1_bookmark_${var.d1_database_name}.json
    EOT
  }
}
```

---

## 6. Verifying Data After Restore

```bash
# Row count sanity check
wrangler d1 execute example project-production-db --remote \
  --command "SELECT name, count(*) as row_count FROM sqlite_master WHERE type='table' GROUP BY name;"

# Spot-check a specific table modified by the bad migration
wrangler d1 execute example project-production-db --remote \
  --command "SELECT * FROM users ORDER BY updated_at DESC LIMIT 10;"

# Confirm application health post-restore
curl -sf "https://api.example.com/health" | jq '.database.status'
# Expected: "ok"
```

---

## Anti-patterns

- Do not restore directly to production without a `--dry-run` first — the dry
  run verifies the bookmark timestamp is within the 30-day window.
- Do not use Time Travel as a substitute for a scheduled export strategy;
  Time Travel is limited to 30 days and is non-portable.  Combine with periodic
  `wrangler d1 export` runs written to R2 for long-term retention.
- Do not restore during peak traffic without putting the Worker behind a
  maintenance mode response first; the brief DB offline period will return 500
  errors to active requests.

## Gotchas

- Time Travel bookmarks older than 30 days are automatically purged by
  Cloudflare, even named ones.  CI must track the bookmark ID and warn when it
  approaches expiry.
- Restoring does not roll back D1 schema migrations recorded in Wrangler's
  `d1_migrations` table — after a time-travel restore you must reconcile the
  migration state manually or re-run `wrangler d1 migrations apply`.
- D1 Time Travel is not available on databases created before August 2023
  (pre-GA era) — check the database creation date before relying on this
  feature in incident response.

## Verification

```bash
# Confirm the database's time travel metadata is accessible
wrangler d1 time-travel info example project-production-db
# Expected output contains min_timestamp within the last 30 days

# List bookmarks
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/time_travel/bookmarks" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" | jq '[.result[] | {id, description, created_at}]'
```

## Related

- `cloudflare-d1-migrations-github-actions.md`
- `terraform-cloudflare-provider-workers-d1.md`
- `pulumi-cloudflare-d1-database-iac.md`
- `cloudflare-r2-backup-restore-strategy.md`
- `disaster-recovery-rto-rpo.md`

## Sources

- https://developers.cloudflare.com/d1/reference/time-travel/
- https://developers.cloudflare.com/d1/platform/backups/
- https://developers.cloudflare.com/api/operations/cloudflare-d1-time-travel
