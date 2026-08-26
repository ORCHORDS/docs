# git-worktree-patterns

**Issue:** Switching branches to review PRs interrupts in-progress work
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stashing or committing WIP to switch context is error-prone and slow.

## Pattern / Solution
git worktree add ../repo-pr-123 pr-123-branch creates a second checkout without re-cloning. Review PR in separate directory while main worktree continues work. Remove with git worktree remove.

## Gotchas
- Each worktree needs its own node_modules install — symlink if disk space is concern
- Cannot checkout same branch in two worktrees simultaneously

## Related
- git-stash-patterns, gitflow-vs-trunk
