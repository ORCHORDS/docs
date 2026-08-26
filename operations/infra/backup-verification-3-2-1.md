# backup-verification-3-2-1

**Issue:** Most teams discover their backups do not work at the same moment they need them: a ransomware detonation, an accidental database drop, or a region outage. The 3-2-1 rule (three copies, two media, one off-site) is widely quoted but routinely misimplemented — copies are taken and never restored, the off-site copy is mutable under the same credentials as production, and nobody has ever timed a full recovery. Modern ransomware operators deliberately enumerate and encrypt backup targets before detonating on production, so an unverified, unisolated backup is effectively no backup at all. This article covers the 3-2-1 baseline and its failure modes, the 3-2-1-1-0 extension (immutability plus verified zero errors), how to run a real restore-testing program, and the metrics that prove recoverability rather than backup-job success.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 3-2-1 baseline and where it fails

1. **Three copies, two media, one off-site.** One production copy plus two backups, on two distinct storage systems (not two volumes on the same array), with one copy in a different failure domain — a different building, region, or cloud account. The rule simultaneously protects against media failure, site loss, and accidental deletion.
2. **Failure: one identity can delete everything.** If a single compromised host holds credentials to every copy, ransomware encrypts all three in sequence. 3-2-1 fails when "three copies" share one identity plane; separation must include credentials and accounts, not just disks.
3. **Failure: backup success is not restorability.** Green job status only proves bytes were written somewhere; it says nothing about whether the data is complete, consistent, or recoverable. Verification must exercise a restore, not read a job log.
4. **Failure: silent scope drift.** The new database, the untracked S3 bucket, and the CI secrets were never added to backup policies. Quarterly audits should enumerate production data stores and diff them against backup coverage — the gap list is the real risk register.

## The 3-2-1-1-0 extension

1. **One immutable or offline copy.** Add a copy that cannot be modified or deleted for a retention window regardless of credentials: S3 Object Lock in compliance mode, WORM tape, or a physically air-gapped rotation. This is the copy ransomware cannot reach and the one you recover from when everything online is encrypted.
2. **Zero errors, verified.** The final digit means automated verification of every backup — checksums, restore drills, and application-level consistency checks with zero unexplained failures. "It probably worked" is a failure state, not a result.
3. **Separation of duties for the last resort.** Break-glass credentials for the immutable copy live in a separate identity store (hardware keys, a distinct account with cross-account roles and no standing access), so compromising production admin does not reach the recovery path.
4. **Retention depth beats frequency alone.** Intruders commonly dwell for weeks before detonating; 30-90 days of point-in-time versions let you recover to before the compromise rather than to the moment of encryption.

## Building a restore-testing program

1. **Quarterly full-scenario drills at minimum.** At least quarterly — the cadence most compliance guidance now expects — pick a real system, restore it to a clean environment, and run the application against it. A drill that stops at "files exist on disk" is theater.
2. **Automate a continuous smoke restore.** Nightly or weekly, automatically restore the latest backup into a scratch environment, run health checks, then destroy it. Continuous verification catches broken backups within hours instead of at disaster time.
3. **Time the recovery against the RTO.** Record restore duration, transfer bottlenecks, and manual steps for every drill. A restore that takes 30 hours against a 4-hour RTO is a finding, not a success — fix throughput or renegotiate the stated RTO.
4. **Test the chain, including people.** Drills should use the actual runbook, the actual on-call engineer, and the documented escalation path; restores that only work when the one backup admin performs them are a bus-factor emergency in waiting.
5. **Verify application consistency, not just files.** Databases need point-in-time recovery tests (WAL or binlog replay) and clusters need state-restore tests; a file-level copy of a database mid-transaction can be unrecoverable garbage that checksums perfectly.

## Metrics and alerting that prove recoverability

1. **Track last-verified age per system.** Dashboard the date each system's backup was last successfully restored and alert when age exceeds policy (for example 90 days); this is the single number leadership should see, because it measures recoverability rather than activity.
2. **Page on verification failures like production incidents.** A failed smoke restore should trigger the same response as a failed deploy; backups silently going bad for a month is exactly how total-loss events happen.
3. **Treat immutability as a hard control.** Ensure Object Lock and WORM settings cannot be altered by any operational role, and alert on attempts to change them — an attacker trying to disable immutability is one of the earliest intrusion signals you will get.
4. **Report coverage percentage, not backup count.** Report the fraction of known data stores with verified, immutable, tested backups and drive it toward 100 percent; shipping a new data store without backup coverage should be a release blocker, not a follow-up ticket.
