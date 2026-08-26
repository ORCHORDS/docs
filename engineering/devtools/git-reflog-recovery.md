# git-reflog-recovery

**Issue:** Commits lost after reset, rebase, or accidental branch deletion
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
git reset --hard or git branch -D loses commits that were not pushed.

## Pattern / Solution
git reflog shows every HEAD movement with timestamps. Find lost commit SHA. git checkout -b recovery SHA to restore as new branch. Reflog kept 90 days by default.

## Gotchas
- Reflog is local only — lost pushes to remote require server-side recovery
- git fsck --lost-found finds dangling commits even without reflog entries

## Related
- git-stash-patterns, git-bisect-debugging
