# git-cherry-pick-patterns

**Issue:** Single fix commit needed on multiple branches
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hotfix on main needs to be applied to release branch without merging all of main.

## Pattern / Solution
git cherry-pick SHA applies commit to current branch. Range: git cherry-pick A..B. Conflicts: resolve then git cherry-pick --continue. --no-commit stages changes without committing for inspection before committing.

## Gotchas
- Cherry-pick creates a new commit with different SHA — diverges history
- git cherry-pick -x adds source commit reference to message for traceability

## Related
- git-interactive-rebase, gitflow-vs-trunk
