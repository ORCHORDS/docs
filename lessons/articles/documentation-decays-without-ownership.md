# documentation-decays-without-ownership

**Issue:** Documentation written without an assigned owner becomes stale, misleading, and eventually more dangerous than no documentation
**Date:** 2026-08-11
**Status:** documented

## What happened
An architecture document described the system as it existed 18 months ago. A new engineer used it to plan a feature integration. They built the integration against a service that had been replaced and deployed it. Production broke. The time lost following outdated documentation exceeded the time that would have been spent asking the team directly.

## The lesson
Every piece of documentation must have a named owner whose job it is to keep it accurate. Link documentation to the code it describes so changes to code prompt documentation review. Set a review cadence (quarterly for architecture docs, per-release for operational runbooks). Treat outdated documentation as a bug.

## Why it matters
Stale documentation actively misleads. A reader assumes documentation is correct — that is its entire purpose. Documentation that was once accurate but no longer is causes more damage than absence, because readers trust it and waste time or make mistakes as a result.

## How to apply
- [ ] Every documentation file must include a `last reviewed` date and a named owner.
- [ ] Add documentation review to release checklists for features or services that own the docs.
- [ ] Link architecture decision records (ADRs) and runbooks from the relevant code files.
- [ ] Set a calendar reminder for quarterly documentation reviews for all critical system docs.
- [ ] Archive or delete documentation that cannot be verified as current — stale docs are worse than no docs.

## Related
- `write-the-runbook-before-the-incident.md`
- `blameless-culture-produces-better-postmortems.md`
