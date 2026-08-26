# commitlint-setup

**Issue:** Commit messages are inconsistent, breaking changelog generation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mixed commit styles make git log and changelogs useless.

## Pattern / Solution
Install @commitlint/cli + @commitlint/config-conventional. Create commitlint.config.js. Add husky commit-msg hook running commitlint. Configure allowed types: feat, fix, docs, chore, refactor, test, ci.

## Gotchas
- Breaking changes need ! after type or BREAKING CHANGE: footer
- commitlint only checks format — semantic-release reads content for versioning

## Related
- git-hooks-husky, conventional-commits, semantic-release-setup
