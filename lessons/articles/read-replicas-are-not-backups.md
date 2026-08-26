# read-replicas-are-not-backups

**Issue:** Teams rely on read replicas for disaster recovery and discover they replicate deletions instantly
**Date:** 2026-08-11
**Status:** documented

## What happened
A team believed their read replica was a backup. A developer dropped a table in production. Within milliseconds, the drop replicated to all read replicas. The "backup" was gone. The last actual backup was 18 hours old. The data loss was confirmed and unrecoverable beyond the 18-hour window.

## The lesson
Read replicas are high-availability tools, not backup tools. They replicate every write, including destructive ones, with near-zero lag. A true backup must be point-in-time, stored separately from the primary, tested for restoration, and delayed enough to survive accidental data destruction.

## Why it matters
Confusing replicas with backups creates a false sense of safety. When something goes wrong, the "backup" is already affected, and the true extent of data loss is discovered at the worst possible moment.

## How to apply
- [ ] Maintain automated point-in-time backups independent of your replication setup.
- [ ] Store backups in a separate account/region from production so a credential compromise can't delete both.
- [ ] Test restoration quarterly — restore to a throwaway environment and verify data integrity.
- [ ] Document clearly in your runbooks: "read replicas are NOT a recovery mechanism for data loss."
- [ ] Consider a delayed replica (e.g., 24-hour lag) as a supplementary recovery tool, not a replacement for backups.

## Related
- `test-your-backups-not-just-your-backup-process.md`
- `two-person-rule-for-production-access.md`
