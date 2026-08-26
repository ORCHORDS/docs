# semantic-release-setup

**Issue:** Manual version bumping and changelog writing is error-prone
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Version in package.json drifts from git tags; CHANGELOG.md not updated consistently.

## Pattern / Solution
Install semantic-release with plugins: commit-analyzer, release-notes-generator, changelog, npm, github. Configure .releaserc.json. Run in CI on main branch only. Reads conventional commits to determine version bump.

## Gotchas
- Requires GITHUB_TOKEN and NPM_TOKEN in CI environment
- First release: must have at least one feat or fix commit; initial version defaults to 1.0.0

## Related
- conventional-commits, commitlint-setup, changesets-versioning
