# two-person-rule-for-production-access

**Issue:** Single-person production access enables both accidental damage and insider abuse
**Date:** 2026-08-11
**Status:** documented

## What happened
An engineer with sole access to the production database ran a migration script with a missing `WHERE` clause during a late-night on-call session. The table was truncated. There was no second set of eyes to catch the error before execution. Recovery took 14 hours.

## The lesson
Any write, delete, or schema-change operation on production databases or infrastructure must require a second human to review and approve the command before execution. This applies to manual SQL, infrastructure scripts, and one-off migrations. Use tooling (e.g., teleport, breakglass workflows) that enforces approval before granting elevated access.

## Why it matters
Two-person rule catches typos, logic errors, and missing WHERE clauses before they execute. It also creates an audit trail and deters insider abuse. The cost is a few minutes of waiting; the benefit is preventing hours or days of recovery.

## How to apply
- [ ] Configure your bastion/access tool to require peer approval for production database write access.
- [ ] Require PR approval from a second engineer for any migration that touches production data.
- [ ] Log all elevated access sessions with the approver's name and timestamp.
- [ ] Treat solo production database writes as a policy violation, not just a bad practice.
- [ ] Run dangerous commands in a `--dry-run` or `EXPLAIN` mode and share the output for review before executing.

## Related
- `never-delete-without-soft-delete-first.md`
- `rotate-credentials-after-every-breach.md`
- `audit-logs-are-append-only.md`
