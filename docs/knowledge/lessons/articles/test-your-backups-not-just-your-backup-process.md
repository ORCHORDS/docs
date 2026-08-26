# test-your-backups-not-just-your-backup-process

**Issue:** Backup jobs succeed silently but produce corrupt or incomplete files that fail on restoration
**Date:** 2026-08-11
**Status:** documented

## What happened
A SaaS company's nightly backup job had been "succeeding" for 14 months. When a ransomware attack hit and they attempted to restore, every backup file for the last 14 months was corrupt — a silent encoding error had been introduced in a dependency update. The backup process worked; the backups did not.

## The lesson
A backup job that exits with code 0 tells you nothing about the usability of the backup file. You must periodically restore from the backup into a test environment and verify the data. This is the only proof that a backup works.

## Why it matters
Backup integrity is invisible until you need it. Silent corruption, incomplete dumps, and permission errors on restore are common. Discovering them during an actual disaster compounds the disaster.

## How to apply
- [ ] Schedule automated restore tests monthly: spin up an isolated environment, restore from last night's backup, run a data integrity check (row counts, checksums on key tables).
- [ ] Alert on restore test failure as a P1 incident — it means your safety net is broken.
- [ ] Verify backup file size is within an expected range after each run (dramatic shrinkage indicates a problem).
- [ ] Store checksums of backup files at creation time and verify on restore.
- [ ] Document the restore procedure and time it — you need to know how long recovery takes before you're in a crisis.

## Related
- `read-replicas-are-not-backups.md`
- `write-the-runbook-before-the-incident.md`
