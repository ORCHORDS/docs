# git-stash-patterns

**Issue:** Stash used incorrectly — changes lost or stack becomes confusing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
git stash pop on wrong branch, or stash list grows indefinitely without naming.

## Pattern / Solution
Always name stashes: git stash push -m wip-auth-refactor. List: git stash list. Apply specific: git stash apply stash@{2}. Include untracked: git stash push -u. Prefer apply over pop to keep stash as backup.

## Gotchas
- Stash is global to repo, not per-branch — easy to apply on wrong branch
- git stash show -p stash@{0} previews diff before applying

## Related
- git-worktree-patterns, git-reflog-recovery
