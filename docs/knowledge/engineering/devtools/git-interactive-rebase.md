# git-interactive-rebase

**Issue:** Messy commit history on feature branch before merge
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Feature branch has WIP commits, fixup commits, and typo-fix commits that should not appear in main history.

## Pattern / Solution
git rebase -i HEAD~N for last N commits. Commands: squash/fixup to combine, reword to edit message, drop to delete, edit to amend. Use git commit --fixup SHA + git rebase -i --autosquash workflow.

## Gotchas
- Never rebase commits already pushed to shared branches
- Editor opens for instructions — configure GIT_EDITOR to avoid nano

## Related
- conventional-commits, git-cherry-pick-patterns, gitflow-vs-trunk
