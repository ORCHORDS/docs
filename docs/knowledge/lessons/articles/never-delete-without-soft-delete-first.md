# never-delete-without-soft-delete-first

**Issue:** Hard-deleting records without a soft-delete layer makes data recovery impossible
**Date:** 2026-08-11
**Status:** documented

## What happened
A support engineer ran a cleanup script in production that permanently removed "inactive" user records. Three days later, those users attempted to log back in and found their accounts gone. Legal was involved. Recovery required restoring a week-old backup, replaying seven days of other users' transactions around the missing rows, and issuing formal breach notifications in two jurisdictions.

## The lesson
Every table that holds user-generated or business-critical data must have a `deleted_at` timestamp column. All "deletes" set that column; a daily job (with human sign-off) purges rows older than your retention policy. Hard deletes are reserved for purge jobs only, never for application code.

## Why it matters
Accidental hard deletes cannot be undone without a restore. A restore affects every other row in the backup, requiring expensive replays, potential data loss for other users, and possible regulatory notification. The blast radius is always larger than expected.

## How to apply
- [ ] Add `deleted_at TIMESTAMPTZ NULL` to every entity table before the first deploy.
- [ ] Scope all default ORM queries with `WHERE deleted_at IS NULL`.
- [ ] Create a separate `purge_deleted_records` job gated behind a human-approval step.
- [ ] Audit any raw SQL scripts for `DELETE FROM` — replace with `UPDATE … SET deleted_at = NOW()`.
- [ ] Document retention periods in the schema README.

## Related
- `test-your-backups-not-just-your-backup-process.md`
- `audit-logs-are-append-only.md`
