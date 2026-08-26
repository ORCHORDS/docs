# git-rebase-vs-merge-2026

**Issue:** A team has a feature branch with 30 commits. The team debates `git rebase main` vs `git merge main` to integrate. The team needs the 2026 reference.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 decision rules

1. **Your local feature branch not yet pushed** → `rebase` (clean history, no noise).
2. **Shared feature branch, multiple collaborators** → `merge` (preserve shared history).
3. **Want linear history in main** → `rebase` then `merge --no-ff` or squash-merge the PR.
4. **PR integration to main** → squash-merge (one commit per PR).
5. **Hotfix branch** → `cherry-pick` or `merge --no-ff` to preserve the "this is a hotfix" marker.

## The 5 mechanics

1. **`git rebase main`** - replays your commits on top of main. Linear history, rewritten SHAs.
2. **`git merge main`** - creates a merge commit. Preserves true history.
3. **`git pull --rebase`** - fetch + rebase instead of fetch + merge. Default for many.
4. **`git rebase -i HEAD~N`** - interactive rebase to squash, fixup, reword commits.
5. **`git merge --squash`** - squash all feature commits into one, no merge commit.

## The 5 anti-patterns

1. **Rebasing shared branches** (`main`, `develop`). Rewrites history for everyone.
2. **Force-push after rebase** without coordinating with team.
3. **Rebasing to hide mistakes** rather than fix them.
4. **Merging main into feature branch repeatedly** (creates criss-cross history).
5. **Squash-merge losing valuable commit history** (Co-authored-by, Fixes #X).

## The 5 best practices

1. **Default to rebase** for local-only feature branches.
2. **Default to merge** for shared branches.
3. **`git pull --rebase`** as the default pull strategy.
4. **Squash-merge PRs** to main; preserve commit history in the feature branch.
5. **Force-push with lease** (`--force-with-lease`) to avoid clobbering others' work.

## Gotchas

- Rebase rewrites SHAs; signed commits get invalidated.
- `--force-with-lease` is safer than `--force` but still destructive.
- Reverting a rebase is hard; reverting a merge is one commit.
- Interactive rebase conflicts compound; resolve each commit in turn.
- Some CI systems cache commit-based artifacts; rebasing breaks the cache.

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/git-rebase
- https://git-scm.com/docs/git-merge
- https://www.atlassian.com/git/tutorials/merging-vs-rebasing
- https://martinfowler.com/articles/branching-patterns.html
