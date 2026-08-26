# audit-logs-are-append-only

**Issue:** Mutable audit logs are useless for forensics and compliance because they can be altered after the fact
**Date:** 2026-08-11
**Status:** documented

## What happened
After a suspected insider data exfiltration, the security team pulled the audit log to reconstruct what the employee had accessed. The audit log was stored in the same database the employee had write access to. The relevant records had been deleted. There was no tamper-evident trail, the investigation failed, and the company could not demonstrate compliance with their data processing agreement.

## The lesson
Audit logs must be written to an append-only store that the application and application-level users cannot modify or delete. This means a separate system with no DELETE or UPDATE permissions granted to application credentials. Use dedicated audit log stores (e.g., immutable S3 buckets, append-only log tables with revoke of UPDATE/DELETE, or purpose-built audit systems).

## Why it matters
An audit log that can be modified by a malicious actor provides no assurance. Regulators, courts, and auditors require tamper-evident records. A mutable audit log is a liability: it provides false comfort and fails at exactly the moment it is needed.

## How to apply
- [ ] Write audit records to a store where application credentials have INSERT only, never UPDATE or DELETE.
- [ ] Enable object lock or WORM (write-once-read-many) on any S3 bucket used for audit logs.
- [ ] Include a cryptographic hash chain or external timestamp service to detect tampering.
- [ ] Separate audit log infrastructure from the primary database — different credentials, different account if possible.
- [ ] Test: attempt to delete an audit record using application credentials — it must fail.

## Related
- `dont-log-pii-in-production.md`
- `two-person-rule-for-production-access.md`
- `insider-threat-is-real.md`
