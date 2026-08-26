# migrations-must-be-backward-compatible

**Issue:** Schema migrations that break the running old code cause downtime during deploy
**Date:** 2026-08-11
**Status:** documented

## What happened
An engineer renamed a heavily used column in a single migration. During the rolling deploy, old pods still running tried to write to the old column name and crashed. New pods read the new column name and found nulls. The window lasted six minutes but caused data corruption in in-flight orders.

## The lesson
Migrations must be backward compatible with the code that runs before, during, and after the deploy. Use an expand-contract pattern: add new column, deploy code that writes both, migrate data, deploy code that reads only new column, drop old column in a later release.

## Why it matters
Zero-downtime deploys are impossible if migrations break old code. Rolling deploys, blue/green, and canary all require that old and new code run simultaneously against the same database.

## How to apply
- [ ] Never rename a column in a single step. Use expand-contract over at least two releases.
- [ ] Never add a NOT NULL column without a default value when old code still runs.
- [ ] Never drop a column until no code references it (grep codebase + one full release cycle).
- [ ] Test migrations against the previous release's application code, not just the new code.
- [ ] Tag migrations that are NOT backward compatible — they require a maintenance window.

## Related
- `always-test-rollback-before-deploying.md`
- `feature-flags-before-code-changes.md`
