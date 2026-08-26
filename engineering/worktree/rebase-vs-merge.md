# rebase-vs-merge

**Issue:** When to `git rebase` vs `git merge`
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a feature branch 5 commits ahead of main. Main has 3
new commits. You `git pull` — now your branch has a merge
commit. The history is cluttered. The PR diff includes "merge
main into branch" noise.

## Root cause
Two valid workflows:
- **Merge workflow:** `git merge main` creates a merge commit.
  Preserves the actual history of parallel development.
- **Rebase workflow:** `git rebase main` replays your commits
  on top of main. Linear history, no merge commit.

Each has tradeoffs. The "right" choice depends on the team +
the branch state.

**Source:** Atlassian — Merging vs Rebasing:
https://www.atlassian.com/git/tutorials/merging-vs-rebasing

> "The golden rule of git rebase is to never use it on public
> branches."

## Decision framework

### Use rebase when:
- **The branch is local-only** (never pushed, or only you have
  it)
- **You want a linear history** in the PR
- **The branch is short-lived** (will be merged and deleted
  soon)
- **No one else is collaborating on the branch**

### Use merge when:
- **The branch is shared** (other people have it, may be
  pushing)
- **You want to preserve the history** of when the branch
  diverged
- **The branch is long-lived** (e.g. a release branch)
- **The merge commit is informative** (e.g. "merge of feature X
  back to main")

### The "rebase on PR" pattern
For a PR that's been reviewed and approved:
```bash
# On the feature branch
git fetch origin
git rebase origin/main
# Now your commits are replayed on top of latest main
# The PR diff is clean (no merge commits)
```

Then the squash-merge on GitHub creates a single commit on main.
The feature branch is deleted.

### The "merge main into branch" pattern (NOT recommended)
```bash
# On the feature branch
git fetch origin
git merge origin/main
# Creates a merge commit
# The PR diff shows "merge main" as a no-op commit (confusing)
```

Don't do this unless you have to (e.g. resolving a conflict
that's only visible with both branches' state).

## Conflict resolution

When rebase produces conflicts:
```bash
git rebase origin/main
# CONFLICT in file.ts
# Resolve the conflict
git add file.ts
git rebase --continue
# If you mess up:
git rebase --abort
```

When merge produces conflicts:
```bash
git merge origin/main
# CONFLICT in file.ts
# Resolve the conflict
git add file.ts
git commit
# (the merge commit is created with your resolution)
```

The rebase process is repeated for each conflicting commit. The
merge process is a single conflict-resolution session.

## Force-push

Rebase rewrites commit hashes. After a rebase, you must
`git push --force-with-lease`:

```bash
# After rebase:
git push --force-with-lease origin feature-branch
```

**NEVER use `git push --force`** (without `--force-with-lease`).
The `--force-with-lease` checks that no one else pushed to the
branch in the meantime, preventing accidental overwrites.

**NEVER force-push to main.** Period. Even with `--force-with-lease`.

## Verification
- **Test:** PR diff has no "merge main" noise after rebase
- **Live:** `git log` is linear in the PR (when rebase workflow)
- **Audit:** Team agreement on which workflow to use

## Gotchas
- **`git pull --rebase`** is the default in many setups. Check
  `git config pull.rebase`.
- **Rebase of a shared branch breaks collaborators.** If Alice
  rebased and Bob had 3 local commits, Bob's `git pull` produces
  duplicates. Always coordinate.
- **`git rebase -i` (interactive rebase)** for squashing commits
  before merging is a powerful cleanup tool. Use before opening
  a PR.
- **The `git rerere` tool** records conflict resolutions and
  reuses them on subsequent rebase/merge. Useful for long-lived
  branches.
- **Merge commits in the feature branch are normal** if multiple
  people are collaborating. They don't pollute main if the PR
  is squash-merged.

## Related
- `worktree/gitlinks-trap.md`
- Atlassian: https://www.atlassian.com/git/tutorials/merging-vs-rebasing
