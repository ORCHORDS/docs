# insider-threat-is-real

**Issue:** Excessive trust granted to internal employees enables data exfiltration and sabotage that external controls cannot prevent
**Date:** 2026-08-11
**Status:** documented

## What happened
A departing engineer with production database access downloaded the entire user table to a personal device two days before their last day. Access logs existed but were not monitored in real time. The exfiltration was discovered three months later during a routine audit. By then, the data had been sold and the engineer was unreachable.

## The lesson
Insider threats require proactive controls: least-privilege access (engineers get only the permissions they need for their current role), real-time monitoring of anomalous data access (large exports, off-hours queries), and immediate access revocation the moment a departure is confirmed.

## Why it matters
Internal actors have legitimate credentials and knowledge of your systems. They bypass most perimeter defenses. Without behavioral monitoring and least-privilege enforcement, you won't know about exfiltration until it is too late.

## How to apply
- [ ] Implement least-privilege: no engineer should have read access to all production user data by default.
- [ ] Alert on anomalous queries: a single session selecting more than X rows from a PII table should page security.
- [ ] Define and enforce an offboarding checklist that revokes all access on the last day (or day of announcement for involuntary termination).
- [ ] Review access grants quarterly — remove access that is no longer needed.
- [ ] Use data loss prevention (DLP) tools to block large file uploads to personal cloud storage from work devices.

## Related
- `audit-logs-are-append-only.md`
- `two-person-rule-for-production-access.md`
- `rotate-credentials-after-every-breach.md`
