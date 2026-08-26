# changesets-versioning

**Issue:** Version bumps in monorepo are manual and inconsistent
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Publishing 10 packages with correct semver bumps and changelogs is error-prone.

## Pattern / Solution
Install @changesets/cli. pnpm changeset prompts for changed packages and bump type. Commit .changeset/*.md files with PRs. In CI: changeset version bumps packages, changeset publish publishes to npm.

## Gotchas
- Pre-release mode: changeset pre enter next creates pre-release versions
- Changeset files must be committed with the PR, not after merge

## Related
- semantic-release-setup, pnpm-workspace-setup, conventional-commits
