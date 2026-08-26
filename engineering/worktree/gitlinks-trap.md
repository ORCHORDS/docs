# worktree-gitlinks-trap

**Issue:** `git worktree add` accidentally committed as a submodule gitlink breaks CI
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main (PR #open-issue-commitlint-gitlinks fixed it)
**Author:** the platform team
**Status:** documented (well-understood pitfall)

## Symptom
You commit a change to a worktree, push, and CI fails:
```
error: git submodule 'frontend' is not registered
fatal: refusing to fetch into non-existent submodule
```

A `git ls-tree HEAD` shows an entry like:
```
160000 commit abc123...  .worktrees/frontend
```

But there's no `.gitmodules` file. The `160000` mode is a gitlink
(submodule reference) — Git is treating the worktree as a submodule
without it being registered as one.

## Root cause
`git worktree add .worktrees/<name> -b <branch>` creates a working
directory. Inside it, `git status` shows the worktree state, and
`git add` can pick up the worktree's `.git` file as a "gitlink".

The `160000` mode is special: it means "this path is a git
reference to another commit." Git uses it for submodules. When Git
sees a `160000` entry without a corresponding `.gitmodules` line,
it can't fetch the submodule and CI breaks.

**Source:** `man git-worktree`:
https://git-scm.com/docs/git-worktree

> "The working tree at `<path>` is connected to the repository
> via a `.git` file (not a directory)."

The `.git` file in a worktree points back to the main repo. If
you `git add` the worktree's root from the main repo, you record
a `160000` entry pointing to the worktree's HEAD commit.

## Fix
Two layers:

### Layer 1: Add `.worktrees/` to `.gitignore`
```gitignore
# Git worktrees — never commit
/.worktrees/
/.worktrees/**
/sessions/  # also commonly a worktree dir
```

If this is in `.gitignore` BEFORE the bad commit, `git add` will
skip the worktree.

### Layer 2: Remove the bad gitlink from history
If the bad commit is already pushed:
```bash
# Find the bad commit
git log --all --diff-filter=A --pretty=format:"%H %s" -- .worktrees/frontend

# Remove the path from the commit (rebase or filter-repo)
# Easiest: revert the PR, then re-open a clean PR
git revert <bad-commit>
# OR
git filter-repo --path .worktrees/frontend --invert-paths
```

For a PR that hasn't been merged, the simplest fix is:
```bash
# On the feature branch
git rm --cached .worktrees/frontend
git commit -m "fix: remove accidentally committed worktree gitlink"
git push --force-with-lease
```

## Verification
- **Test:** `git ls-tree HEAD` should NOT contain any `160000` entries
  for `.worktrees/`
- **CI:** PR builds pass after the fix is applied
- **Live:** the platform main has 0 gitlinks after PR #open-issue-commitlint-gitlinks

## Gotchas
- **`git worktree add` doesn't auto-add to `.gitignore`.** You must
  add it manually OR use a worktree directory that's already gitignored
  (like `node_modules/`'s parent).
- **The the platform repo's `.gitignore` MUST list `.worktrees/`** before
  any agent starts a worktree. The first commit-with-worktree is
  the one that bites.
- **Some workflows use a separate `worktrees/` (with a 'w') to
  avoid collision with the system-wide convention.** Both are fine;
  the key is consistency.
- **If you see `160000` in `git ls-files --stage`, that's a
  gitlink.** `git rm --cached` it before any further work.

## Related
- the platform PR #open-issue-commitlint-gitlinks (the fix)
- `git worktree` docs: https://git-scm.com/docs/git-worktree
- Submodule vs worktree: worktrees are working directories OF the
  same repo; submodules are nested repos. Don't mix them up.
